
const postgres = require('postgres');
const sql = postgres('postgresql://postgres:postgres@localhost:5432/nexuswars');

async function main() {
  const teams = await sql`SELECT id, name FROM teams WHERE name ILIKE '%LORD OF THOSE BELOW ME%'`;
  console.log('Matching teams:', teams);
  for (const t of teams) {
    const subs = await sql`SELECT id, artifact_key, status FROM submissions WHERE team_id = ${t.id}`;
    console.log('Submissions found:', subs.length);
    if (subs.length > 0) {
      const ids = subs.map(s => s.id);
      await sql`DELETE FROM submission_ratings WHERE submission_id = ANY(${ids})`;
      await sql`DELETE FROM match_participants WHERE submission_id = ANY(${ids})`;
      await sql`DELETE FROM submissions WHERE team_id = ${t.id}`;
      console.log('Wiped all submissions for', t.name);
    }
  }
  await sql.end();
}
main().catch(console.error);
