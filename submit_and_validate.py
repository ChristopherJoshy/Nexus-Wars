import os, sys, uuid, json, time
sys.path.insert(0, '/app')
from db import get_conn, execute, query
from storage import put_file

team_id = "b55e8afa-69e1-4fb0-8532-f6598dfc8835"
user_id = "f2a80cd4-03b3-4ebb-8b43-b6c41cc8a2a8"
bot_file = "/app/Escanor.py" 
sub_id = str(uuid.uuid4())
artifact_key = f"submissions/{team_id}/{sub_id}/Escanor.py"

print(f"Submitting Escanor.py for team {team_id} (Submission ID: {sub_id})...")

# Upload to S3/MinIO
put_file(artifact_key, bot_file)

# Insert submission into DB
conn = get_conn()
execute(conn, """
    INSERT INTO submissions (id, team_id, user_id, status, artifact_key, engine_version)
    VALUES (%s, %s, %s, 'queued', %s, '2026.1.0')
""", (sub_id, team_id, user_id, artifact_key))

# Enqueue validation job with early timestamp to run immediately
execute(conn, """
    INSERT INTO jobs (type, payload_json, status, created_at)
    VALUES ('validate', %s, 'pending', '2020-01-01 00:00:00+00')
""", (json.dumps({"submission_id": sub_id}),))

conn.commit()
print("Submission inserted & validation job queued!")

# Poll for status update
for _ in range(30):
    time.sleep(2)
    rows = query(conn, "SELECT status, reject_reason FROM submissions WHERE id = %s", (sub_id,))
    if rows:
        status, reject_reason = rows[0][0], rows[0][1]
        print(f"Current Submission Status: {status}")
        if status == 'active':
            print("SUCCESS! Bot state changed to ACTIVE!")
            break
        elif status in ('rejected', 'errored'):
            print(f"FAILED! Bot status is {status}. Reject Reason: {reject_reason}")
            break

conn.close()
