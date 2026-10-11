# Running the worker on a server

The worker is the only part that uses a browser and a model. It runs in one Docker container on an
Ubuntu EC2 instance (a `t3.large`, 2 vCPU and 8 GB, is plenty for one run at a time). It makes
outbound connections only (Supabase, Anthropic, neatlogs and the sites it visits), so the instance
needs **no inbound ports** except SSH.

Before the first run, `supabase/schema.sql` must have been run in the Supabase SQL editor (the
latest version: it is safe to run again).

## 1. Clone

```bash
git clone https://github.com/devs-dv/first-user.git
cd first-user
```

If the repository is private, GitHub asks for a username and a personal access token (with read
access to the repository) instead of a password.

## 2. Create the env file (by hand, outside the repository)

```bash
install -m 600 /dev/null "$HOME/first-user.env"
nano "$HOME/first-user.env"
```

Put these lines in it, with your real values after the `=`:

```
ANTHROPIC_API_KEY=
NEATLOGS_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
BRAIN_MODEL=haiku
```

- One `NAME=value` per line, **no quotes**, no spaces around `=`, no `export`. Docker's `--env-file`
  keeps quotes as part of the value.
- `BRAIN_MODEL` is `haiku` (cheap) or `sonnet` (the default if the line is left out).
- Never commit this file, never put it in the repository, and never paste it in a chat.
- The image contains no secrets: it is built without this file and only receives it when it runs.

## 3. Build

```bash
docker build -t first-user-worker --build-arg AGENT_VERSION=$(git rev-parse --short HEAD) worker/
```

The first build takes a few minutes (it installs Chrome and the Python packages). The commit id is
saved with each run as its agent version.

## 4. Check the image before running it for real

These do not touch the queue:

```bash
# Chrome is installed, and the worker runs as a non-root user.
docker run --rm first-user-worker google-chrome-stable --version
docker run --rm first-user-worker id

# Stagehand finds Chrome.
docker run --rm first-user-worker python -c "from stagehand.browser import _find_chrome_path; print(_find_chrome_path())"

# One real visit, with no database: should print steps and then a JSON result with "outcome".
docker run --rm --init --shm-size=1g --env-file "$HOME/first-user.env" \
  --security-opt seccomp="$PWD/worker/chrome-seccomp.json" first-user-worker \
  python run_once.py --url https://example.com --goal "Say what this page is for."
```

Expected: `uid=10001(worker)`, `/usr/bin/google-chrome-stable`, and the visit finishing with an outcome
(not `error`) in under a minute. Run these from the repository root, so `$PWD/worker/chrome-seccomp.json` exists.

## 5. Run

```bash
docker run -d --name first-user-worker \
  --restart unless-stopped \
  --init \
  --shm-size=1g \
  --env-file "$HOME/first-user.env" \
  --stop-timeout 600 \
  --security-opt no-new-privileges:true \
  --security-opt seccomp="$PWD/worker/chrome-seccomp.json" \
  --cap-drop ALL \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=5 \
  first-user-worker
```

| Flag | Why |
|---|---|
| `-d` | runs in the background |
| `--restart unless-stopped` | comes back after a crash and after the instance reboots, but not after you stop it |
| `--init` | a tiny init process reaps Chrome's child processes, so zombies do not pile up |
| `--shm-size=1g` | Chrome keeps shared memory in `/dev/shm`, which is only 64 MB by default and makes tabs crash |
| `--env-file` | passes the secrets at run time, so they are not in the image or in the command line |
| `--stop-timeout 600` | `docker stop` waits up to 10 minutes for a run in progress to finish before it is killed |
| `--security-opt no-new-privileges:true`, `--cap-drop ALL` | the container gets no extra privileges (Chrome needs none) |
| `--security-opt seccomp=.../chrome-seccomp.json` | lets Chrome's own sandbox start (see "Chrome's sandbox" below). Run the command from the repository root |
| `--log-opt max-size=10m`, `max-file=5` | rotates the logs: at most 50 MB kept |

On start the worker launches Chrome once, before taking any work, and logs one line:

```
[preflight] browser ok (headless=True, viewport 1280x800)
```

If Chrome cannot start with its sandbox, the worker prints why and exits with code 3 instead of
failing every run later (Docker then restarts it every few seconds: `docker stop` it and fix the cause).
A `WARNING:` on that line means Chrome is running **without** its sandbox (see below).

Docker is enabled at boot on Ubuntu by default. If `docker ps` is empty after a reboot, run
`sudo systemctl enable --now docker`.

## 6. Logs and health

```bash
docker logs -f --tail 100 first-user-worker     # follow the log (Ctrl+C leaves the container running)
docker ps                                       # STATUS shows "(healthy)" after about a minute
docker inspect --format '{{.State.Health.Status}}' first-user-worker
```

Within a minute of starting you should see `Worker started ...` and then, while the queue is empty,
one line a minute:

```
[health] 2026-10-11T13:03:15Z idle for 1m02s, queue empty | 0 runs since start (0 failed) | up 1m02s | agent 1a2b3c4
```

While a run is in progress the log shows its steps instead, and no health line.

## 7. Update

```bash
cd ~/first-user
git pull
docker build -t first-user-worker --build-arg AGENT_VERSION=$(git rev-parse --short HEAD) worker/
docker stop first-user-worker      # finishes the run in progress first (up to 10 minutes), then exits
docker rm first-user-worker
```

Then run the `docker run -d --name first-user-worker ...` command from step 5 again.

## 8. Stop

```bash
docker stop first-user-worker      # finishes the run in progress, saves it, then exits
docker rm first-user-worker        # only if you want to remove the container
```

`docker stop` sends SIGTERM. The worker then claims no new run, finishes and saves the one in
progress, and exits (code 0). If it is killed anyway (a second `docker stop`, `docker kill`, a power
cut), the run stays "running" and the worker's stale-run sweep marks it failed 15 minutes later, so
the web page shows it as failed rather than waiting forever.

## What the settings do

The image sets these; you do not need to put them in the env file.

| Variable | Value | Meaning |
|---|---|---|
| `HEADLESS` | `true` | Chrome runs with no window |
| `CHROME_SANDBOX` | not set (on) | Chrome's own sandbox stays on; `false` turns it off (see below) |
| `CHROME_PATH` | `/usr/bin/google-chrome-stable` | where Stagehand looks for Chrome |
| `CLEAN_RUN_FILES` | `true` | a run's local screenshots are deleted once saved (they are in storage) |
| `VIEWPORT_WIDTH` / `VIEWPORT_HEIGHT` | `1280` / `800` | the page size, always, so click coordinates are right |
| `DEVICE_SCALE_FACTOR` | `1.0` | no display scaling |
| `AGENT_VERSION` | the commit id | saved on each run |

### Chrome flags

Stagehand adds a long list of its own defaults (no first-run prompts, no background networking,
the extension and DevTools settings it needs). On top of them, the worker's launch adds these:

| Flag | Why |
|---|---|
| `--headless` | no window: a server has no display |
| `--window-size=1280,800`, `--force-device-scale-factor=1.0` | a fixed size and scale; the page's viewport is also set explicitly after launch |
| (no `--no-sandbox`) | Chrome's sandbox stays on. Stagehand adds `--no-sandbox` by itself when the process runs as root or `CI` is set, so the image does neither, and the preflight warns if it happens anyway |
| `--disable-gpu` | a server has no GPU; avoids GPU-process crashes (pages render in software) |
| `--disable-dev-shm-usage` | added automatically only if `/dev/shm` is under 512 MB (a container started without `--shm-size`) |
| `--proxy-server=...`, `--proxy-bypass-list=<-loopback>` | every request goes through the worker's local egress guard, also loopback |
| `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` | WebRTC could otherwise open UDP connections that skip the guard |

### Chrome's sandbox

Chrome runs as the same user as the worker, and the worker's environment holds the Supabase,
Anthropic and neatlogs keys. Chrome's sandbox is what separates a page's renderer from that
process: with it off, a renderer exploit from a hostile page could read the keys from
`/proc/<worker pid>/environ`. So the sandbox stays **on**.

Chrome builds the sandbox from new user and PID namespaces and a chroot. Docker's default seccomp
profile only allows the calls for that (`clone` with namespace flags, `unshare`, `setns`, `chroot`)
to containers that hold `CAP_SYS_ADMIN` or `CAP_SYS_CHROOT`, and this container drops every
capability. `worker/chrome-seccomp.json` is Docker's own current default profile with **one rule
added**, allowing those four calls without a condition. Nothing else changes: `mount`, `ptrace`,
`pivot_root` and the capabilities stay blocked, and inside a user namespace the calls give no
privileges over the host. Regenerate it with `python worker/make_chrome_seccomp.py` (it fetches the
current default from github.com/moby/profiles).

If the preflight fails with "No usable sandbox", the likely causes are: the container was started
without the `--security-opt seccomp=...` line; or the host forbids unprivileged user namespaces. On
Ubuntu 24.04 check `sysctl kernel.apparmor_restrict_unprivileged_userns` and
`sysctl kernel.unprivileged_userns_clone`. Do not work around it by turning the sandbox off in the
env file: the better fallbacks are to fix the host setting, or to run the browser in a separate
container that holds none of the keys. Setting `CHROME_SANDBOX=false` is possible, and the
preflight then says `WARNING: ... sandbox is OFF` at every start.

### Notes

- **Memory:** one run uses roughly 1 to 1.5 GB (Chrome plus the worker). One run at a time is the
  design, so the 8 GB of a `t3.large` is ample.
- **The instance metadata service:** the egress guard stops the browser reaching `169.254.169.254`,
  but also limit it at the instance (IMDSv2 with a hop limit of 1, so containers cannot reach it):
  `aws ec2 modify-instance-metadata-options --instance-id <id> --http-tokens required --http-put-response-hop-limit 1`
- **Chrome updates:** the image installs the current stable Chrome when it is built. Rebuild
  (step 7) to pick up a newer one.
- **Architecture:** Chrome for Linux is built for amd64 and arm64; a `t3` is amd64. The Python
  packages are pinned in `worker/requirements.lock.txt` (all have Linux wheels for Python 3.11).

## If something is wrong

| Symptom in `docker logs` | Likely cause and fix |
|---|---|
| `Chrome installation not found` | the image was built wrong: rebuild; check step 4 |
| `[preflight] The browser could not be started`, `No usable sandbox` | the container is missing `--security-opt seccomp=.../chrome-seccomp.json`, or the host forbids unprivileged user namespaces: see "Chrome's sandbox" above |
| `[preflight] ... WARNING: ... sandbox is OFF` | `CHROME_SANDBOX=false`, `CI` is set, or the container runs as root: Chrome runs without its sandbox; remove the cause |
| Pages crash or are blank, `Aw, Snap` in screenshots | the container was started without `--shm-size=1g` |
| `KeyError: 'NEATLOGS_API_KEY'` | the env file path is wrong or the line is missing |
| `Database error: ... retrying in 10s` | wrong `SUPABASE_URL` or service key, or the schema has not been run |
| `runs.trace_id does not exist yet` (or `entry`, `first_impression`) | run the latest `supabase/schema.sql`; runs are saved without it until then |
| `docker ps` shows `(unhealthy)` | the worker's loop is stuck: `docker logs --tail 50`, then `docker restart first-user-worker` |
| The disk is filling | `docker system df`; `docker image prune` removes old image builds |
