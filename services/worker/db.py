"""PostgreSQL access (psycopg 3)."""
import psycopg
from config import DATABASE_URL


def get_conn():
    conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    conn.execute("SET statement_timeout = '30000'")
    return conn


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
