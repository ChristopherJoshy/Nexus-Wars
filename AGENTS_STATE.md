## Objective
- Build "Nexus Wars": production-ready 1v1 AI battle competition (Orbit-Wars-inspired + energy), deterministic engine, sandboxed untrusted bots, Glicko-2 ladder. Phase 2 backend + sandbox VALIDATED. Docker stack RUNNING. Web app scaffolded with S3 upload + replay viewer.

## Important Details
- Hard requirements: 1v1 only; ≤500 steps; match <3 min; energy system; ≤5 submissions/team/day; latest-2 active; private validation; replays only post-match (JSON + viewer).
- **WSL IS ALREADY WSL2** (Ubuntu 24.04, kernel 6.18) — earlier "WSL1" note was stale. Unprivileged user namespaces work. sudo password is `123`.
- Protocol (validated by tests): bot actions are angle-based `[source_planet_id, angle_radians, num_ships]`; planet tuple `[id, owner, x, y, radius, ships, production, energy, energyCap, energyRegen]` (owner = index 1); bot emits one JSON array (or `{"action":[...]}`) per turn over newline-delimited stdin/stdout.
- Sandbox = 4 layers (per design): (1) nsjail empty netns, (2) seccomp, (3) host iptables egress drop / gVisor, (4) defense-in-depth. All proven on WSL2.
- nsjail 3.4's bundled kafel table misses modern syscalls (rseq/statx/faccessat2/clone3/stat/lstat/fstat) → seccomp policy fails to compile → Python bots killed at startup. FIXED by patching kafel's `amd64_syscalls.c` (saved at `deploy/nsjail-patch/amd64_syscalls.c`) and building nsjail from source (`deploy/build_nsjail.sh`).
- seccomp.policy: ALLOW list of safe syscalls + `socket` family (allowed because the empty netns blocks all inet egress regardless — netns is the real network control); `DEFAULT KILL_PROCESS` kills ptrace/mount/etc. No `#` comments, no `POLICY` wrapper (kafel DSL).
- nsjail.cfg: `mode: ONCE`, `clone_newnet`, `clone_newpid`, `clone_newuts`, rlimits (cpu 30s/as 512MB/fsize 1MB/nofile 64/nproc 64), seccomp_policy_file, read-only bind mounts of /lib /lib64 /usr /etc /bin, rw /work + /tmp. Hostname "bot".

## Work State
### Completed
- Phase 1 engine: 10/10 tests pass (`tests/test_nexus_wars.py`, `tests/test_subprocess_runner.py`), determinism verified.
- Phase 2 backend: `services/worker/jobs.py` (validation + rated + Glicko-2 update), `main.py` (concurrent SKIP LOCKED loop + matchmaker tick), `matchmaker.py` (rating-proximity pairing), `config.py`, `db.py`, `storage.py`, `rating/glicko2.py` + `rating/test_glicko2.py`.
- Sandbox FULLY BUILT + VALIDATED + WIRED INTO PRODUCTION:
  - `deploy/seccomp.policy` (final, clean), `deploy/nsjail.cfg` (hardened).
  - `deploy/build_nsjail.sh` + `deploy/nsjail-patch/amd64_syscalls.c` (reproducible nsjail build).
  - `deploy/sandbox_test.sh` + `tests/fixtures/sandbox_bot.py` (pentest suite).
  - `deploy/Dockerfile.worker`: builds nsjail from source (patched table), ships cfg+policy to `/etc/nsjail/`, `USE_NSJAIL=1` default.
  - Fixed `jobs.py` `_sandbox_cmd()` double-`sys.executable` bug.
  - Pentest 3/3: compute runs, net egress → "Network is unreachable" (blocked), ptrace → SIGSYS (killed).
  - End-to-end production path verified: real bot subprocess under nsjail played 500-step match vs `random`, winner decided in ~325 ms.
- Phase 3 web app scaffolded (`services/web/`):
  - Next.js 16 App Router + Tailwind CSS + shadcn/ui.
  - Drizzle ORM schema matching `migrations/0001_init.sql` (users, teams, team_members, submissions, ratings, matches, match_participants, jobs, replay_objects).
  - **Firebase Auth** (replaced Better Auth): Google OAuth via Firebase JS SDK. Server-side token verification via Firebase Admin SDK.
  - API routes: teams (create/join-by-code), submissions (upload + daily limit), leaderboard, replays.
  - Pages: home, leaderboard, team, submit, replay viewer.
  - Build passes (`npm run build` clean).
  - `services/web/src/lib/s3.ts` — S3/MinIO client (AWS SDK v3) with `getS3()` singleton.
  - Submissions API: uploads to MinIO at `submissions/{teamId}/{subId}/{filename}`, enqueues `validate` job.
  - Replay API: fetches replay JSON from MinIO using `match.replayKey`, returns full replay data.
  - Canvas replay viewer (`src/components/replay/ReplayRenderer.tsx`): renders planets (colored by owner, radius, ships, energy bar), fleets (dots + trail), sun, grid. Playback controls (play/pause/prev/next/speed).
  - `.env.local` created with all required env vars for local dev.
- Docker stack RUNNING (Docker Desktop 29.6.2 + Compose v5.3.1):
  - `deploy/Dockerfile.worker`: builds nsjail from source (patched kafel table with `--recurse-submodules`), `flex`+`bison` added, ships cfg+policy to `/etc/nsjail/`, `USE_NSJAIL=1` default.
  - `deploy/docker-compose.yml`: postgres:16, minio, mc (auto-create bucket), worker (privileged for nsjail). Fixed env var mismatch (S3_* → MINIO_*).
  - Worker image built and running: connects to postgres, polls with `SELECT ... FOR UPDATE SKIP LOCKED`, max_concurrent=4.
  - Fixed `ENGINE_VERSION` missing from `config.py` (was imported in `jobs.py` but not defined).
  - DB schema updated and migrated to support Firebase Auth (`firebase_uid`, `image`, `updated_at` columns added, Better Auth tables dropped) using drizzle-kit push.

### Blocked / Not started
- End-to-end submission flow untested (web upload → MinIO → worker validation → DB update).
- Canvas viewer not tested against real replay data (built from spec, needs a real match to verify).

## Next Move
1. Generate a real `BETTER_AUTH_SECRET` and set up Google OAuth credentials for auth.
2. End-to-end test: create team via API, submit a bot, verify worker picks up validation job.
3. (Optional hardening) consider `clone_newuser` + drop to nobody in nsjail.cfg once workdir ownership in the container is sorted.

## Relevant Files
- `deploy/seccomp.policy`, `deploy/nsjail.cfg` — final sandbox config.
- `deploy/build_nsjail.sh`, `deploy/nsjail-patch/amd64_syscalls.c` — reproducible nsjail build.
- `deploy/Dockerfile.worker`, `deploy/docker-compose.yml` — worker image/infra.
- `deploy/sandbox_test.sh`, `tests/fixtures/sandbox_bot.py` — pentest suite.
- `services/worker/jobs.py` — `_sandbox_cmd()` + `bot_runner()` (production nsjail launch; double-python bug fixed).
- `services/worker/engine/nexus_wars/run_match.py` — `SubprocessRunner` (sandbox_cmd path) + `run_match`.
- `services/worker/main.py`, `matchmaker.py`, `config.py`, `db.py`, `storage.py`, `rating/*` — backend.
- `services/web/` — Next.js web app (scaffolded, builds clean):
  - `src/lib/db/schema.ts` — Drizzle ORM schema (9 tables matching migration).
  - `src/lib/firebase-client.ts`, `src/lib/auth-client.ts` — Firebase Auth (Google OAuth via JS SDK).
  - `src/lib/firebase-admin.ts`, `src/lib/get-session.ts` — Firebase Admin token verification for API routes.
  - `src/lib/s3.ts` — S3/MinIO client (AWS SDK v3).
  - `src/app/api/` — API routes (teams, submissions with S3 upload, leaderboard, replays from S3).
  - `src/app/` — Pages (home, leaderboard, team, submit, replay).
  - `src/components/replay/ReplayRenderer.tsx` — Canvas-based replay visualization.
  - `.env.local` — Local dev env vars.
- `migrations/0001_init.sql` — PostgreSQL schema (source of truth for Drizzle).
- `tests/test_nexus_wars.py`, `tests/test_subprocess_runner.py`, `services/worker/rating/test_glicko2.py` — test gates (all pass).
- `docs/superpowers/plans/2026-07-20-web-app-scaffold.md` — implementation plan.
- Built nsjail binary (ephemeral): `/tmp/nsjail/nsjail` on WSL.
