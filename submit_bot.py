import os, sys, uuid
sys.path.insert(0, '/app')
from db import get_conn, execute
from storage import put_file

team_id = "a4476ea0-d6e9-4a99-95c6-401379555065"
user_id = "f2a80cd4-03b3-4ebb-8b43-b6c41cc8a2a8"
bot_file = "/app/Escanor.py" 
sub_id = str(uuid.uuid4())
artifact_key = f"submissions/{team_id}/{sub_id}/Escanor.py"

# Upload to S3/MinIO
# Upload to S3/MinIO
put_file(artifact_key, bot_file)

# Insert to DB
conn = get_conn()
execute(conn, """
    INSERT INTO submissions (id, team_id, user_id, status, artifact_key)
    VALUES (%s, %s, %s, 'queued', %s)
""", (sub_id, team_id, user_id, artifact_key))
conn.commit()

print(f"Successfully submitted Escanor.py as {sub_id} under team {team_id}!")
