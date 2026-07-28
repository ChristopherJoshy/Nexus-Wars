# Nexus Wars — AGENTS

## Stacks

| Stack | Dir | Run | Test | Lint |
|---|---|---|---|---|
| Engine | `services/worker/engine/nexus_wars/` | — | `python -m pytest tests/ -q` | `ruff check .` |
| Worker | `services/worker/` | `docker compose -f deploy/docker-compose.yml up -d worker` | — | — |
| Web | `services/web/` | `npm run dev` (port 3000) | — | `npm run lint`; `npm run build` (typecheck + build) |
| Infra | `deploy/` | `docker compose -f deploy/docker-compose.yml up -d postgres minio mc` | — | — |

No web-app test runner exists (`npm test` not configured).

## Key gotchas

- **Next.js 16** (not 15). Read `services/web/node_modules/next/dist/docs/` before writing code. Breaking changes.
- **nsjail requires Linux** (WSL2 or native). Windows cannot run it.
- **nsjail 3.4 kafel bug**: missing modern syscalls (rseq, statx, clone3, stat, lstat, fstat). Patch at `deploy/nsjail-patch/amd64_syscalls.c`. Build script: `deploy/build_nsjail.sh`. Needs `--recurse-submodules` + `flex` + `bison`.
- **Env var split**: web app uses `S3_*` keys; worker uses `MINIO_*` keys. Not unified.
- **Worker `config.py`**: `os.uname()` for `WORKER_ID` — Linux-only (falls back to `"worker"`).
- **S3 storage keys**: `submissions/{teamId}/{subId}/{filename}`, `validation/{submissionId}.json`, `rated/{matchId}.json`.
- **Seccomp.policy**: kafel DSL. No `#` comments. No `POLICY` wrapper. `send`/`recv` undefined in kafel → use `sendto`/`recvfrom`.
- **Engine**: planet tuple `[id, owner, x, y, radius, ships, production, energy, energyCap, energyRegen]`. Fleet tuple `[id, owner, x, y, angle, from_planet_id, ships, launchedStep]`. Comets removed.
- **Firebase Auth** (replaces Better Auth). Frontend: `firebase-client.ts` + `auth-client.ts`. Server: `firebase-admin.ts` + `get-session.ts`. Worker: `firebase_init.py`. Service account mounted at `/etc/firebase/service-account.json` in Docker.
- **Vendor dir** `services/worker/engine/vendor/kaggle-environments/` — do not modify.

## Architecture

```
Web (Next.js 16)  ──HTTP──>  Worker (Python, nsjail sandbox)
     │                            │
     ├── Postgres (Docker)        ├── Postgres (same)
     └── MinIO (Docker)           └── MinIO (same)
```

Web app runs on Windows Node. Infra runs in Docker (WSL2 backend). Worker is `privileged: true` for nsjail namespaces.

## Commands

```bash
# All Python tests
python -m pytest tests/ -q

# Single engine test
python -m pytest tests/test_nexus_wars.py::test_determinism -q

# Glicko-2 tests (standalone, no DB)
python services/worker/rating/test_glicko2.py

# Web app
cd services/web && npm run dev       # dev server
cd services/web && npm run build     # typecheck + production build
cd services/web && npm run lint      # ESLint

# Docker
docker compose -f deploy/docker-compose.yml up -d postgres minio mc
docker compose -f deploy/docker-compose.yml up -d worker
docker compose -f deploy/docker-compose.yml build worker
docker compose -f deploy/docker-compose.yml down
```

## State

Full state tracker at `AGENTS_STATE.md`.
