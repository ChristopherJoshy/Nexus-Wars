<div align="center">
  <img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0b1020,35:1d4ed8,70:7c3aed,100:22d3ee&height=190&section=header&text=Nexus%20Wars&fontSize=62&fontColor=ffffff&animation=twinkling&fontAlignY=36&desc=Write%20a%20bot.%20Launch%20it%20into%20orbit.&descAlignY=58&descSize=17" alt="Nexus-Wars animated header" />

  <p>
    <img src="https://img.shields.io/badge/Web-Next.js%2016-111827?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js 16" />
    <img src="https://img.shields.io/badge/Worker-Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python worker" />
    <img src="https://img.shields.io/badge/Rating-Glicko--2-7C3AED?style=for-the-badge" alt="Glicko-2" />
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-67E8F9?style=for-the-badge" alt="MIT License" /></a>
  </p>
</div>

## 🌠 The game

Nexus Wars is a bot-battle platform set in a deterministic space strategy simulation. Players submit Python agents; a separate worker extracts and runs them in a Linux sandbox, records match results, and updates Glicko-2 ratings.

<p align="center"><img src="services/web/public/nexus_wars_schematic.jpg" width="78%" alt="Nexus Wars game schematic" /></p>

## 🛰️ System map

```mermaid
flowchart LR
  A[Next.js web app] --> B[PostgreSQL]
  A --> C[MinIO object storage]
  A --> D[Submission queue]
  D --> E[Python worker]
  E --> F[nsjail sandbox and game engine]
  F --> G[Match result and Glicko-2]
  G --> B
```

## 🧰 Stack

| Layer | Tools |
|---|---|
| Web | Next.js 16, React, TypeScript, Tailwind, Drizzle |
| Identity | Firebase Auth |
| Worker | Python 3, nsjail sandbox |
| Data | PostgreSQL 16, MinIO |
| Local environment | Docker Compose |

## 🚀 Local development

Prerequisites: Docker Desktop/WSL2, Node.js 20+, Python 3.10+.

```bash
git clone https://github.com/ChristopherJoshy/Nexus-Wars.git
cd nexus-wars
cd services/web
npm install
npm run dev
```

From the repository root, start local services with Docker Compose:

```bash
docker compose -f deploy/docker-compose.yml up -d postgres minio mc
docker compose -f deploy/docker-compose.yml up -d worker
```

Firebase service-account configuration and the `NEXT_PUBLIC_FIREBASE_*` variables are needed for authenticated flows. See the deployment files and environment examples; keep credentials outside Git.

## 🧪 Tests

```bash
python -m pytest tests/ -q
python services/worker/rating/test_glicko2.py
```

## 🧑‍🚀 Bot contract

A submitted Python agent receives an observation and game configuration, then returns actions in the engine's expected format. Read `services/worker/engine/nexus_wars/nexus_wars.json` and the included local test tools before writing an agent.

## 🗂️ Layout

```text
services/web/       Next.js app and API
services/worker/    match orchestration, engine, rating and sandbox
deploy/             Docker Compose and container setup
migrations/         database migrations
tests/              worker and engine tests
```

## 📄 License

MIT. See [`LICENSE`](LICENSE).

## ⚠️ Notes

The worker sandbox is Linux-specific and relies on nsjail. A local development setup is not a production security review; inspect sandbox limits and submission handling before exposing it to untrusted uploads.
