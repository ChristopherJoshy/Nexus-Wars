# Nexus Wars

A competitive AI-programming game platform where bots written by players battle in a space-themed real-time strategy simulation. Players submit Python agents, and the platform runs head-to-head matches in a sandboxed environment with Glicko-2 rating.

## Architecture

```
Web (Next.js 16)  ──HTTP──>  Worker (Python, nsjail sandbox)
     │                            │
     ├── Postgres (Docker)        ├── Postgres (same)
     └── MinIO (Docker)           └── MinIO (same)
```

- **Web app** — Next.js 16 (App Router), Firebase Auth, Drizzle ORM, Tailwind CSS 4
- **Worker** — Python 3 job loop with nsjail sandbox (Linux), deterministic game engine, Glicko-2 rating
- **Infra** — PostgreSQL 16, MinIO (S3-compatible object storage)

## Quick Start

### Prerequisites

- Docker Desktop (WSL2 backend on Windows)
- Node.js 20+
- Python 3.10+

### Web App (Development)

```bash
cd services/web
npm install
npm run dev        # http://localhost:3000
```

### Infrastructure

```bash
docker compose -f deploy/docker-compose.yml up -d postgres minio mc
docker compose -f deploy/docker-compose.yml up -d worker
```

### Setting Up Firebase Auth

1. Create a Firebase project and enable Google sign-in
2. Download the service account JSON and place it at the project root as `nexuswars2026-firebase-adminsdk-<hash>.json`
3. Set the `FIREBASE_SERVICE_ACCOUNT_PATH` env var (or Docker volume mount at `/etc/firebase/service-account.json`)
4. Set `NEXT_PUBLIC_FIREBASE_*` env vars for the web app

### Running Tests

```bash
# Engine tests
python -m pytest tests/ -q

# Glicko-2 tests
python services/worker/rating/test_glicko2.py
```

## Submitting a Bot

1. Create a team on the web app
2. Write a Python bot that implements the `agent()` function
3. Upload via the submission page
4. The worker validates, runs matches, and updates ratings

### Bot API

```python
def agent(observation, configuration):
    # observation: dict with 'planets' and 'fleets' arrays
    # configuration: dict with game settings
    # Return: list of [source, target, ship_ratio] actions
    return []
```

See the game engine spec at `services/worker/engine/nexus_wars/nexus_wars.json` for full details.

## Project Structure

```
├── services/
│   ├── web/              # Next.js 16 frontend + API
│   │   └── src/
│   │       ├── app/      # Pages and API routes
│   │       ├── components/  # React components
│   │       └── lib/      # Auth, DB, S3 utilities
│   └── worker/           # Python backend
│       ├── engine/       # Game engine (nexus_wars)
│       ├── rating/       # Glicko-2 implementation
│       ├── jobs.py       # Job runner
│       └── matchmaker.py # Matchmaking logic
├── deploy/               # Docker Compose, Dockerfiles, sandbox config
├── migrations/           # PostgreSQL schema migrations
├── docs/                 # Documentation
└── tests/                # Python test suite
```

## Deployment

The worker requires Linux with nsjail for sandboxing. See `deploy/Dockerfile.worker` for the container build.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui |
| Auth | Firebase Auth (Google OAuth) |
| Database | PostgreSQL 16 (Drizzle ORM / raw SQL) |
| Storage | MinIO (S3-compatible) |
| Backend | Python 3, nsjail sandbox |
| Rating | Glicko-2 |
| Infrastructure | Docker Compose |