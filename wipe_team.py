import sys
sys.path.insert(0, '/app')
from db import get_conn, execute, query

team_id = "a4476ea0-d6e9-4a99-95c6-401379555065"

conn = get_conn()

# Get submission IDs for this team
sub_rows = query(conn, "SELECT id FROM submissions WHERE team_id = %s", (team_id,))
sub_ids = [r[0] for r in sub_rows]
print(f"Found {len(sub_ids)} submissions to delete.")

# Get match IDs involving this team
match_rows = query(conn, "SELECT id FROM matches WHERE team_a_id = %s OR team_b_id = %s", (team_id, team_id))
match_ids = [r[0] for r in match_rows]
print(f"Found {len(match_ids)} matches to delete.")

# 1. Delete jobs associated with these matches or submissions
execute(conn, "DELETE FROM jobs WHERE type = 'run_match' AND payload_json->>'match_id' IN (SELECT id::text FROM matches WHERE team_a_id = %s OR team_b_id = %s)", (team_id, team_id))
execute(conn, "DELETE FROM jobs WHERE type = 'validate' AND payload_json->>'submission_id' IN (SELECT id::text FROM submissions WHERE team_id = %s)", (team_id,))

# 2. Delete matches
execute(conn, "DELETE FROM matches WHERE team_a_id = %s OR team_b_id = %s", (team_id, team_id))

# 3. Delete submission ratings
execute(conn, "DELETE FROM submission_ratings WHERE submission_id IN (SELECT id FROM submissions WHERE team_id = %s)", (team_id,))

# 4. Delete submissions
execute(conn, "DELETE FROM submissions WHERE team_id = %s", (team_id,))

# 5. Delete team ratings
execute(conn, "DELETE FROM ratings WHERE team_id = %s", (team_id,))

# 6. Delete team members
execute(conn, "DELETE FROM team_members WHERE team_id = %s", (team_id,))

# 7. Delete team
execute(conn, "DELETE FROM teams WHERE id = %s", (team_id,))

conn.commit()
conn.close()

print(f"Successfully and completely wiped team {team_id}!")
