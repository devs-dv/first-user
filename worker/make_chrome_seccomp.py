"""Build chrome-seccomp.json: Docker's current default seccomp profile plus what Chrome's sandbox needs.

Usage: python make_chrome_seccomp.py

Chrome's own sandbox isolates each page's renderer in new user and PID namespaces and a chroot.
Docker's default profile allows `clone` with namespace flags, `unshare`, `setns` and `chroot`
only for a container that holds CAP_SYS_ADMIN or CAP_SYS_CHROOT, which this worker's container
deliberately does not (--cap-drop ALL). So Chrome fails with "No usable sandbox", and the choice
used to be to switch the sandbox off.

This adds ONE rule to the default profile and changes nothing else:

    allow clone, unshare, setns, chroot (no conditions)

Not added: mount, pivot_root, ptrace, or any capability. `clone3` keeps the default's ENOSYS
answer, so glibc falls back to `clone`. Inside a user namespace these calls grant no privileges
over the host; the kernel needs the capability in the namespace being changed.

The source is the profile Docker itself ships: github.com/moby/profiles, seccomp/default.json.
"""

import json
import sys
import urllib.request
from pathlib import Path

SOURCE = "https://raw.githubusercontent.com/moby/profiles/main/seccomp/default.json"
ADDED = {
    "names": ["clone", "unshare", "setns", "chroot"],
    "action": "SCMP_ACT_ALLOW",
}
OUT = Path(__file__).parent / "chrome-seccomp.json"


def build(default: dict) -> dict:
    profile = json.loads(json.dumps(default))  # a copy
    if profile.get("defaultAction") == "SCMP_ACT_ALLOW":
        raise SystemExit("the source profile allows everything by default; refusing to build on it")
    profile["syscalls"].append(ADDED)
    return profile


def main() -> None:
    with urllib.request.urlopen(SOURCE, timeout=30) as response:  # noqa: S310 - fixed https URL
        default = json.load(response)
    profile = build(default)
    OUT.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(default['syscalls'])} rules in the default, {len(profile['syscalls'])} now)")


if __name__ == "__main__":
    sys.exit(main())
