"""
Nexus Wars worker — job loop.

Polls the `jobs` table with SELECT ... FOR UPDATE SKIP LOCKED so multiple
worker processes/instances share the queue without double-claiming. Runs up to
MAX_CONCURRENT matches in parallel (one thread each); every match is fully
isolated (its own bot subprocesses, tmpfs dir, nsjail namespace), so N matches
run concurrently with no shared state and deterministic from their own seed.
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine", "nexus_wars"))

from config import POLL_INTERVAL, MAX_CONCURRENT, WORKER_ID
from db import get_conn, execute, execute_returning
import jobs
import matchmaker
import feed_generator

MIGRATIONS_DIR = os.environ.get("MIGRATIONS_DIR", "/migrations")


def wait_for_db(retries=30, delay=2):
    """Block until PostgreSQL accepts connections."""
    for attempt in range(1, retries + 1):
        try:
            conn = get_conn()
            conn.close()
            print(f"[db] connected on attempt {attempt}")
            return
        except Exception as exc:
            print(f"[db] attempt {attempt}/{retries} failed: {exc}")
            time.sleep(delay)
    raise RuntimeError("could not connect to database after retries")


def _split_statements(sql):
    """Split SQL into individual statements, stripping comments and blanks."""
    import re
    # Remove line comments and block comments
    sql = re.sub(r'--[^\n]*', '', sql)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    # Split on semicolons that are not inside quotes
    stmts = re.split(r';\s*(?=(?:\'(?:[^\'\\]|\\.)*\')*[^\'"]*$)', sql)
    return [s.strip() for s in stmts if s.strip()]


def run_migrations():
    """Apply SQL migration files statement-by-statement (idempotent).

    Each statement is committed individually so that a failure in one
    (e.g. "already exists") does not roll back statements that already
    succeeded earlier in the same file.
    """
    conn = get_conn()
    try:
        for name in sorted(os.listdir(MIGRATIONS_DIR)):
            if not name.endswith(".sql"):
                continue
            path = os.path.join(MIGRATIONS_DIR, name)
            with open(path, "r") as f:
                sql = f.read()
            stmts = _split_statements(sql)
            applied = 0
            for stmt in stmts:
                try:
                    conn.execute(stmt)
                    conn.commit()
                    applied += 1
                except Exception as exc:
                    conn.rollback()
                    msg = str(exc)
                    if any(kw in msg for kw in ("already exists", "does not exist",
                                                 "duplicate key", "multiple rows")):
                        pass  # expected on re-run
                    else:
                        print(f"[migrate] WARNING {name}: {msg}")
            if applied:
                print(f"[migrate] {name} ({applied} statements)")
    finally:
        conn.close()


def claim_job():
    """Atomically claim one pending job; returns (id, type, payload) or None."""
    conn = get_conn()
    try:
        row = execute_returning(conn,
            "UPDATE jobs SET status='running', started_at=now(), worker_id=%s "
            "WHERE id = (SELECT id FROM jobs WHERE status='pending' "
            "ORDER BY type ASC, created_at LIMIT 1 FOR UPDATE SKIP LOCKED) "
            "RETURNING id, type, payload_json",
            (WORKER_ID,))
        conn.commit()
        return row
    finally:
        conn.close()


def process(job):
    job_id = job[0]
    conn = get_conn()
    try:
        jobs.run_job(job, conn)
        execute(conn, "UPDATE jobs SET status='done', finished_at=now() WHERE id=%s", (job_id,))
        conn.commit()
        print(f"[ok] job {job_id} ({job[1]})")
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        err_str = str(e)
        # Thread exhaustion: exit so Docker restarts the container cleanly
        if "can't start new thread" in err_str:
            print(f"[fatal] thread exhaustion detected, restarting worker: {e}")
            import sys as _sys
            _sys.exit(1)
        execute(conn, "UPDATE jobs SET status='failed', error=%s, finished_at=now() WHERE id=%s",
                (err_str[:2000], job_id))
        if job[1] == "validate":
            try:
                import json
                payload = job[2] if isinstance(job[2], dict) else json.loads(job[2])
                sub_id = payload.get("submission_id")
                if sub_id:
                    execute(conn,
                            "UPDATE submissions SET status='rejected', reject_reason='worker_error' "
                            "WHERE id=%s AND status='queued'", (sub_id,))
            except Exception as sub_err:
                print(f"[fail] failed to reject submission {job_id}: {sub_err}")
        conn.commit()
        print(f"[fail] job {job_id}: {e}")
    finally:
        conn.close()


def main():
    import threading
    wait_for_db()
    run_migrations()
    feed_generator.start_feed_generator()
    sem = threading.Semaphore(MAX_CONCURRENT)
    matchmake_every = max(1, int(10 / POLL_INTERVAL))  # ~every 10s
    ticks = matchmake_every - 1  # run matchmaker immediately on first tick
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as ex:
        print(f"worker {WORKER_ID} started (max_concurrent={MAX_CONCURRENT})")
        while True:
            ticks += 1
            if ticks % matchmake_every == 0:
                c = None
                try:
                    c = get_conn()
                    matchmaker.enqueue_matches(c)
                except Exception as e:  # noqa: BLE001
                    err_str = str(e)
                    if "can't start new thread" in err_str:
                        print(f"[fatal] thread exhaustion in matchmaker, restarting: {e}")
                        import sys as _sys
                        _sys.exit(1)
                    print(f"[matchmaker] error: {e}")
                finally:
                    if c:
                        c.close()
            if not sem.acquire(blocking=False):
                time.sleep(POLL_INTERVAL)
                continue
            job = claim_job()
            if job is None:
                sem.release()
                time.sleep(POLL_INTERVAL)
                continue
            ex.submit(_run_with_release, process, job, sem)


def _run_with_release(fn, job, sem):
    try:
        fn(job)
    finally:
        sem.release()


if __name__ == "__main__":
    main()
