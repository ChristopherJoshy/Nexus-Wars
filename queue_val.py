import os, sys, json
sys.path.insert(0, '/app')
from db import get_conn, execute

conn = get_conn()
execute(conn, """
    INSERT INTO jobs (type, payload_json, status)
    VALUES ('validate', %s, 'pending')
""", (json.dumps({"submission_id": "4df7d898-dbac-47dd-a90d-e7dbdca7a848"}),))
conn.commit()

print("Queued validate job!")
