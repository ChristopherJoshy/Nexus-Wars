import db

conn = db.get_conn()

print("=== MATCH STATUS COUNTS ===")
rows = db.query(conn, "SELECT status, COUNT(*) FROM matches GROUP BY status ORDER BY status;")
for r in rows:
    print(f"Status: {r[0]:<12} | Count: {r[1]}")

print("\n=== MATCH THROUGHPUT (LAST 5 MINS) ===")
t_rows = db.query(conn, "SELECT COUNT(*) FROM matches WHERE status = 'finished' AND finished_at > now() - interval '5 minutes';")
print(f"Finished in last 5 minutes: {t_rows[0][0]}")

t1_rows = db.query(conn, "SELECT COUNT(*) FROM matches WHERE status = 'finished' AND finished_at > now() - interval '1 minute';")
print(f"Finished in last 1 minute:  {t1_rows[0][0]}")
