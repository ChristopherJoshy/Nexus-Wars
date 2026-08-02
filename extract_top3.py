import os, sys
sys.path.insert(0, '/app')
from db import get_conn, query
from storage import get_file

conn = get_conn()
teams = query(conn, """
    SELECT t.id, t.name, r.rating 
    FROM teams t 
    JOIN ratings r ON r.team_id = t.id 
    ORDER BY r.rating DESC LIMIT 3
""", ())

out_dir = "/app/extracted_agents"
os.makedirs(out_dir, exist_ok=True)

rank = 1
for row in teams:
    team_id, team_name, team_rating = row[0], row[1], row[2]
    subs = query(conn, """
        SELECT s.id, sr.rating, s.artifact_key 
        FROM submissions s 
        LEFT JOIN submission_ratings sr ON sr.submission_id = s.id 
        WHERE s.team_id = %s AND s.status = 'active' 
        ORDER BY sr.rating DESC NULLS LAST LIMIT 1
    """, (team_id,))
    
    if subs:
        sub_id, sub_rating, artifact_key = subs[0][0], subs[0][1], subs[0][2]
        if artifact_key:
            filename = artifact_key.split('/')[-1]
            safe_team = "".join([c if c.isalnum() else "_" for c in team_name])
            dest_filename = f"Rank{rank}_{safe_team}_Bot_{filename}"
            dest_path = os.path.join(out_dir, dest_filename)
            print(f"Downloading Rank {rank}: {team_name} (Team Elo: {team_rating:.1f}) -> {dest_filename} (Bot Elo: {sub_rating:.1f})")
            get_file(artifact_key, dest_path)
            rank += 1
        else:
            print(f"Missing artifact key for {team_name}")
    else:
        print(f"Team {team_name} has no active agents.")
