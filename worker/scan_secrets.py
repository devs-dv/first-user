"""Look for secrets in the repository and its history, without printing any.

Usage: python scan_secrets.py

Reports file paths, line numbers and counts only, never the matched text. It looks for:
  * key-shaped strings (the patterns trace_safety.py redacts);
  * the exact value of every secret-named environment variable of this process, taken after
    worker/.env is loaded the way the worker loads it. (web/.env.local is not read.)
It scans the working tree (skipping .git, virtualenvs, node_modules, build output and the
.env files themselves) and every commit and ref in git history.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
ROOT = HERE.parent
load_dotenv(HERE / ".env")

import trace_safety  # noqa: E402

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", ".next", "__pycache__", ".entire", "egg-info"}
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pyc", ".woff", ".woff2", ".pdf", ".zip")
KEY_SHAPES = {
    "anthropic or sk- key": r"sk-ant-[A-Za-z0-9_\-]{8,}|\bsk-[A-Za-z0-9_\-]{20,}",
    "JWT (Supabase key)": r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}",
    "supabase sb_ key": r"\bsb_(?:secret|publishable)_[A-Za-z0-9_\-]{8,}",
    "bearer token": r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{16,}",
}


def env_secrets() -> dict[str, str]:
    return {
        name: value for name, value in os.environ.items()
        if trace_safety._ENV_SECRET_NAME.search(name) and len(value.strip()) >= trace_safety._MIN_ENV_SECRET_CHARS
    }


def scan_tree(secrets: dict[str, str]) -> list[tuple[str, int, str]]:
    shapes = {label: re.compile(pattern) for label, pattern in KEY_SHAPES.items()}
    hits = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in SKIP_DIRS or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.name.startswith(".env") or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for label, pattern in shapes.items():
                if pattern.search(line):
                    hits.append((relative.as_posix(), number, label))
            for name, value in secrets.items():
                if value in line:
                    hits.append((relative.as_posix(), number, f"value of {name}"))
    return hits


def scan_history(secrets: dict[str, str]) -> list[str]:
    """Paths (at a commit) containing a key shape or a secret value, anywhere in history."""
    revisions = subprocess.run(["git", "rev-list", "--all"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    if not revisions:
        return []
    found: set[str] = set()
    combined = "|".join(f"(?:{pattern})" for pattern in KEY_SHAPES.values())
    result = subprocess.run(["git", "grep", "-l", "-I", "-E", "-e", combined, *revisions], cwd=ROOT,
                            capture_output=True, text=True)
    found.update(line for line in result.stdout.splitlines() if line)
    if secrets:
        # Pattern file, so the values never appear in a process's arguments.
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            handle.write("\n".join(secrets.values()) + "\n")
        try:
            result = subprocess.run(["git", "grep", "-l", "-I", "-F", "-f", handle.name, *revisions], cwd=ROOT,
                                    capture_output=True, text=True)
            found.update(line for line in result.stdout.splitlines() if line)
        finally:
            os.unlink(handle.name)
    return sorted(found)


def main() -> None:
    secrets = env_secrets()
    print(f"Secret-named environment variables with a value: {len(secrets)} "
          f"({', '.join(sorted(secrets)) or 'none'}). Their values are checked but never printed.")
    revisions = subprocess.run(["git", "rev-list", "--all", "--count"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    tree = scan_tree(secrets)
    print(f"\nWorking tree: {len(tree)} match(es)")
    for path, line, label in tree:
        print(f"  {path}:{line}  {label}")

    history = scan_history(secrets)
    print(f"\nGit history ({revisions} commits, all refs): {len(history)} file(s) with a match")
    for entry in history[:50]:
        commit, _, path = entry.partition(":")
        print(f"  {commit[:8]}:{path}")

    ignored = subprocess.run(["git", "check-ignore", "worker/.env", "web/.env.local"], cwd=ROOT,
                             capture_output=True, text=True).stdout.split()
    print(f"\nEnv files ignored by git: {', '.join(ignored) or 'none of worker/.env, web/.env.local'}")
    tracked = subprocess.run(["git", "ls-files", "--", "*.env", "*.env.*", ".env*"], cwd=ROOT,
                             capture_output=True, text=True).stdout.split()
    print(f"Env files tracked by git: {', '.join(tracked) or 'none'}")


if __name__ == "__main__":
    main()
