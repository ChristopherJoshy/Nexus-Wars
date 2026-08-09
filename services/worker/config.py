"""Worker configuration from environment."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def env(key, default=None):
    return os.environ.get(key, default)


DATABASE_URL = env("DATABASE_URL", "postgresql://nexus:nexus@localhost:5432/nexus")

# Storage: local filesystem by default; set MINIO_ENDPOINT to use S3/MinIO.
STORAGE_DIR = env("STORAGE_DIR", "/data/replays")
MINIO_ENDPOINT = env("MINIO_ENDPOINT")
MINIO_KEY = env("MINIO_KEY")
MINIO_SECRET = env("MINIO_SECRET")
MINIO_BUCKET = env("MINIO_BUCKET", "nexus-replays")

SUBMISSIONS_DIR = env("SUBMISSIONS_DIR", "/data/submissions")
ENGINE_DIR = env("ENGINE_DIR", os.path.join(BASE_DIR, "engine", "nexus_wars"))
ENGINE_VERSION = env("ENGINE_VERSION", "2026.1.0")

# Match parameters
# Per-step timeout: 2000 ms per agent move (allows slow bots to respond).
# Match timeout: 8.5 minutes max.
ACT_TIMEOUT = float(env("ACT_TIMEOUT", "2.0"))
RUN_TIMEOUT = float(env("RUN_TIMEOUT", "510"))
EPISODE_STEPS = int(env("EPISODE_STEPS", "80"))
SHIP_SPEED = float(env("SHIP_SPEED", "6.0"))
ENERGY_CAP = int(env("ENERGY_CAP", "100"))
ENERGY_REGEN = int(env("ENERGY_REGEN", "5"))
LAUNCH_ENERGY_COST = int(env("LAUNCH_ENERGY_COST", "20"))

# Sandbox (Phase 6 hardening lives here; off by default for local dev)
USE_NSJAIL = env("USE_NSJAIL", "0") == "1"
NSJAIL_CFG = env("NSJAIL_CFG", os.path.join(BASE_DIR, "..", "deploy", "nsjail.cfg"))

MAX_CONCURRENT = int(env("MAX_CONCURRENT", "4"))
POLL_INTERVAL = float(env("POLL_INTERVAL", "2.0"))
WORKER_ID = env("WORKER_ID", os.uname().nodename if hasattr(os, "uname") else "worker")
