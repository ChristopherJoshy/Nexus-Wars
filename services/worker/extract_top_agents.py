import os
import shutil
import storage
from db import get_conn, query

def main():
    conn = get_conn()
    out_dir = "/tmp/extracted_agents"
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Get top 4 teams
    rows = query(conn,
        "SELECT s.team_id, MAX(rating) as max_rating "
        "FROM submission_ratings sr "
        "INNER JOIN submissions s ON sr.submission_id = s.id "
        "WHERE s.status = 'active' "
        "GROUP BY s.team_id "
        "ORDER BY max_rating DESC LIMIT 4", ())
    
    top_teams = [r[0] for r in rows]
    
    for rank, team_id in enumerate(top_teams, 1):
        team_info = query(conn, "SELECT name FROM teams WHERE id=%s", (team_id,))
        team_name = team_info[0][0] if team_info else str(team_id)
        
        # Get active submissions for this team
        active_subs = query(conn,
            "SELECT id, artifact_key, created_at FROM submissions "
            "WHERE team_id=%s AND status='active' ORDER BY created_at DESC",
            (team_id,))
        
        for idx, (sub_id, artifact_key, _) in enumerate(active_subs, 1):
            if not artifact_key:
                continue
            
            clean_team_name = "".join(c for c in team_name if c.isalnum() or c in (" ", "_", "-")).strip()
            filename = os.path.basename(artifact_key)
            out_name = f"Rank{rank}_{clean_team_name}_Bot{idx}_{filename}"
            local_path = os.path.join(out_dir, out_name)
            
            print(f"Downloading {artifact_key} to {local_path}...")
            storage.get_file(artifact_key, local_path)

if __name__ == "__main__":
    main()
