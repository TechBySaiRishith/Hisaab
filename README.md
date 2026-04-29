# Hisaab

> Hindi for *"account / settle-up"* — what you do at the end of every match night.

Slot-fair badminton cost splitter. Computes each player's share of court + shuttle (slot-based with ₹5 rounding) and drafts a pre-filled `wa.me` payment message per friend. Self-hosted on Raspberry Pi, accessed over Tailscale from anywhere.

## How it works

1. Set up venues with their per-hour court rate and per-hour shuttle rate (one-time).
2. Add your regular players to the roster, with phone numbers (one-time).
3. After a session: open the app, walk through the 7-step wizard (setup → players → courts & hours → bookers → slot grid → shuttles → review), tap **Finalize**.
4. Result page shows each player's owe / credit / net, rounded to nearest ₹5. Tap **Send via WhatsApp** per player to pre-fill a message in your WhatsApp; for players without saved phones, tap **Copy message** instead.

## Stack

- Python 3.12 · FastAPI · async SQLAlchemy 2.0 · SQLite + Litestream backups
- Jinja2 templates · HTMX · Tailwind CSS v4 (custom OKLCH design system)
- Docker (linux/arm64) · GitHub Actions CI · GitHub Container Registry
- structlog JSON logs · Prometheus `/metrics` endpoint

---

## Local development (Windows / macOS / Linux)

### Prerequisites

- Python 3.12+ on `PATH`
- (Optional) Docker Desktop for testing the production image locally
- The Tailwind standalone binary is downloaded into the project root once

### First-time setup

```bash
git clone <your-repo-url>
cd hisaab
make install      # creates .venv, installs deps, installs pre-commit hooks
```

### Build CSS

```bash
make tailwind          # one-shot build
# or
make tailwind-watch    # watches templates and rebuilds on change
```

### Run locally

```bash
make dev               # http://localhost:8080
```

You'll need to set `DATABASE_URL` in your environment or in a `.env` file at the project root:

```bash
echo 'DATABASE_URL=sqlite+aiosqlite:///./data/hisaab.db' > .env
```

The DB is created automatically; on first run, run migrations:

```bash
.venv/Scripts/alembic upgrade head        # Windows
# or
.venv/bin/alembic upgrade head            # macOS / Linux
```

### Lint and type-check

```bash
make lint
make type
make ci                # both
```

### Windows note

If `pytest.exe`, `uvicorn.exe`, etc. fail with an Application Control / Smart App Control block, run them via `python -m`:

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
python -m alembic upgrade head
python -m ruff check .
python -m mypy app/domain app/services
```

---

## Deploy to Raspberry Pi

The deployment model:

- **Code lives in GitHub.** Pushing to `main` triggers GitHub Actions to build a multi-arch Docker image and push it to GitHub Container Registry (GHCR) as `ghcr.io/<your-gh-user>/hisaab:latest`.
- **The Pi pulls that image.** `docker compose` on the Pi runs the app + a Litestream sidecar that backs up SQLite continuously to `/opt/hisaab/backup/`.
- **You access it over Tailscale** at `http://<pi-tailscale-name>:8080`.

### Step 1 — Prepare the Pi

This assumes Raspberry Pi OS (Bookworm or newer) on a Pi 4 / Pi 5 (ARM64).

SSH into the Pi, then:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# log out and back in for the group change to take effect

# Verify
docker --version
docker compose version
```

If Tailscale isn't already set up:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Take note of the Pi's Tailscale hostname (e.g. `raspberrypi.tail-scale.ts.net` — `tailscale status` shows it).

### Step 2 — Set up GHCR access

The Pi needs to authenticate to GHCR to pull your private/public image.

On GitHub:
1. Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token
2. Scopes: `read:packages` (only)
3. Copy the token

On the Pi:

```bash
echo "<your-token>" | docker login ghcr.io -u <your-github-username> --password-stdin
```

### Step 3 — Push the code and let CI build the image

From your dev machine:

```bash
git remote add origin git@github.com:<your-gh-user>/hisaab.git
git push -u origin main
```

Watch the build at `https://github.com/<your-gh-user>/hisaab/actions`. The `docker-build` job (~3 minutes) cross-builds linux/arm64 and pushes to GHCR.

After it finishes, your image is live at:
```
ghcr.io/<your-gh-user>/hisaab:latest
```

By default the image is **private**. To pull it on the Pi without auth, make it public: GitHub → your profile → Packages → hisaab → Package settings → Change visibility → Public. Or leave it private and use the GHCR auth from Step 2.

### Step 4 — Bootstrap the Pi (one-time)

From your dev machine:

```bash
PI_HOST=<pi-tailscale-name> make pi-bootstrap
```

This SSHes in, creates `/opt/hisaab/data` and `/opt/hisaab/backup`, and copies `docker/docker-compose.yml` + `docker/litestream.yml` into `/opt/hisaab/`.

### Step 5 — First deploy

From your dev machine:

```bash
GITHUB_OWNER=<your-gh-user> PI_HOST=<pi-tailscale-name> make pi-deploy
```

This:
1. Replaces the `{{GITHUB_OWNER}}` placeholder in `/opt/hisaab/docker-compose.yml`
2. Pulls the latest image
3. Starts the stack (`docker compose up -d`) — the container runs `alembic upgrade head` automatically before uvicorn starts
4. Waits 5 seconds, then curls `http://localhost:8080/health` to confirm

### Step 6 — Open it on your phone

Over Tailscale:

```
http://<pi-tailscale-name>:8080
```

That's the only URL you need. Pin it as a home-screen shortcut on your phone — it's mobile-first by design.

---

## First-time app setup (after deploy)

1. Open the app. Tap **Settings** in the bottom nav.
2. Set **Your name** at the top of Settings (e.g. "Sai") and tap save. This is the `is_self` player — it's auto-created and pre-included in every session.
3. Optionally set your **UPI ID** (interpolated into outgoing WhatsApp messages).
4. Go to **Settings → Venues** and add your venue with hourly court rate + hourly shuttle rate.
5. Go to **Roster** and add your regular players one by one — name, emoji, primary WhatsApp phone (with country code, e.g. `+919876543210`).
6. Done. Tap the **+ New Match** floating button on the home screen and walk the wizard.

---

## Operations

### Updating to a new version

```bash
# 1. Make changes locally, commit, push
git add . && git commit -m "feat: …" && git push

# 2. Wait for CI to publish (~3 min)

# 3. Roll out to the Pi
GITHUB_OWNER=<your-gh-user> PI_HOST=<pi-tailscale-name> make pi-deploy
```

### View logs

```bash
ssh <pi-tailscale-name> 'cd /opt/hisaab && docker compose logs -f --tail=100 app'
```

Logs are structured JSON. Pipe through `jq` for readability:
```bash
ssh <pi-tailscale-name> 'cd /opt/hisaab && docker compose logs --tail=100 app' | jq
```

### Database backups (Litestream)

The Litestream sidecar continuously streams the SQLite WAL to `/opt/hisaab/backup/`. Snapshots taken every 24h, retained for 7 days.

To restore from backup:

```bash
ssh <pi-tailscale-name>
cd /opt/hisaab
docker compose down
docker run --rm -v $(pwd)/data:/data -v $(pwd)/backup:/backup litestream/litestream:0.3 \
  restore -o /data/hisaab.db file:///backup/hisaab
docker compose up -d
```

### Manual SQLite snapshot (off-Pi backup)

```bash
scp <pi-tailscale-name>:/opt/hisaab/data/hisaab.db ./backup-$(date +%Y%m%d).db
```

### Metrics & health

```bash
curl http://<pi-tailscale-name>:8080/health   # → {"status":"ok"}
curl http://<pi-tailscale-name>:8080/metrics  # Prometheus format
```

### Stop / restart the stack

```bash
ssh <pi-tailscale-name> 'cd /opt/hisaab && docker compose down'
ssh <pi-tailscale-name> 'cd /opt/hisaab && docker compose up -d'
```

---

## Troubleshooting

**`make pi-deploy` fails at the curl health check.**
SSH in and check container logs (`docker compose logs app`). Most common cause: migration failure on a new schema.

**Image not found when pulling.**
Either CI hasn't built it yet (check Actions tab) or the package is still private (see Step 3 — make public, or `docker login ghcr.io` from the Pi).

**Tailscale name doesn't resolve.**
Run `tailscale status` on both your dev box and the Pi — both must be up and on the same tailnet. Use the Pi's tailscale IP (`100.x.y.z`) as a fallback.

**Schema change broke an existing session.**
Sessions store rate snapshots, so old finalized sessions are immune to venue rate changes. But schema migrations can break old session loads if a column changes. Test migrations on a copy of the prod DB before deploying:

```bash
scp <pi-tailscale-name>:/opt/hisaab/data/hisaab.db ./prod-copy.db
DATABASE_URL=sqlite+aiosqlite:///./prod-copy.db .venv/Scripts/alembic upgrade head
```

---

## Architecture

Full design spec: `docs/superpowers/specs/2026-04-29-badminton-splitter-design.md` *(historical filename — refers to Hisaab)*.

Implementation plan: `docs/superpowers/plans/2026-04-29-badminton-splitter-plan.md`.
