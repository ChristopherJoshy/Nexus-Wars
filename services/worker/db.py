"""PostgreSQL access (psycopg 3)."""
import psycopg
from config import DATABASE_URL


def get_conn():
    return psycopg.connect(DATABASE_URL, autocommit=False)


def run_migrations(conn, path):
    with open(path, "r") as f:
        conn.execute(f.read())
    conn.commit()


def query(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def execute(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())


def execute_returning(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()
