import sys
sys.path.insert(0, '/app')
from db import get_conn
from matchmaker import _enqueue_locked

conn = get_conn()
created = _enqueue_locked(conn, limit_override=5)
print(f"Manually created {created} matches with new Elo matchmaking algorithm.")
conn.close()
