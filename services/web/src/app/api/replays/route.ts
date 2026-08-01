import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { matches, teams, users, matchParticipants, submissions } from "@/lib/db/schema";
import { eq, or, and, desc, inArray } from "drizzle-orm";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const teamIdParam = searchParams.get("teamId");
  const submissionId = searchParams.get("submissionId");

  try {
    const baseWhere = eq(matches.status, "finished");

    // If submissionId is provided (e.g. from Submissions page "Episodes" button),
    // strictly filter matches played by that specific bot submission.
    // Otherwise, if teamIdParam is provided (e.g. from Leaderboard link), filter by team.
    const filterWhere = submissionId
      ? or(eq(matches.submissionAId, submissionId), eq(matches.submissionBId, submissionId))
      : teamIdParam
        ? or(eq(matches.teamAId, teamIdParam), eq(matches.teamBId, teamIdParam))
        : undefined;

    const whereClause = filterWhere
      ? and(baseWhere, filterWhere)
      : and(baseWhere, eq(matches.kind, "rated"));

    const recentMatches = await db
      .select({
        id: matches.id,
        seed: matches.seed,
        kind: matches.kind,
        status: matches.status,
        winner: matches.winner,
        reason: matches.reason,
        replayKey: matches.replayKey,
        scores: matches.scores,
        startedAt: matches.startedAt,
        finishedAt: matches.finishedAt,
        createdAt: matches.createdAt,
        teamAId: matches.teamAId,
        teamBId: matches.teamBId,
        submissionAId: matches.submissionAId,
        submissionBId: matches.submissionBId,
      })
      .from(matches)
      .where(whereClause)
      .orderBy(desc(matches.finishedAt), desc(matches.createdAt))
      .limit(500);

    const allTeams = await db
      .select({
        id: teams.id,
        name: teams.name,
        image: users.image,
      })
      .from(teams)
      .leftJoin(users, eq(teams.ownerId, users.id));

    const teamMap = new Map(allTeams.map((t) => [t.id, { name: t.name, image: t.image }]));

    const matchIds = recentMatches.map((m) => m.id);
    const allParticipants = matchIds.length > 0
      ? await db
          .select()
          .from(matchParticipants)
          .where(inArray(matchParticipants.matchId, matchIds))
      : [];
    const ratingMap = new Map<string, { rating: number; rd: number; change: number | null }>();
    for (const p of allParticipants) {
      const change = p.ratingAfter != null && p.ratingBefore != null
        ? Math.round(p.ratingAfter - p.ratingBefore)
        : null;
      const data = {
        rating: p.ratingAfter ?? p.ratingBefore ?? 600,
        rd: p.rdAfter ?? p.rdBefore ?? 350,
        change,
      };
      if (p.teamId) ratingMap.set(`${p.matchId}:${p.teamId}`, data);
      if (p.submissionId) ratingMap.set(`${p.matchId}:${p.submissionId}`, data);
    }

    const formattedMatches = recentMatches.map((m) => {
      const teamAData = m.teamAId ? teamMap.get(m.teamAId) : null;
      const teamBData = m.teamBId ? teamMap.get(m.teamBId) : null;

      const teamAName = teamAData?.name || "Team Alpha";
      const teamBName = teamBData?.name || "Team Beta";
      const teamAImage = teamAData?.image || null;
      const teamBImage = teamBData?.image || null;

      const aRating = (m.submissionAId && ratingMap.get(`${m.id}:${m.submissionAId}`)) ||
                      (m.teamAId && ratingMap.get(`${m.id}:${m.teamAId}`)) || null;
      const bRating = (m.submissionBId && ratingMap.get(`${m.id}:${m.submissionBId}`)) ||
                      (m.teamBId && ratingMap.get(`${m.id}:${m.teamBId}`)) || null;

      let aChange = aRating?.change ?? null;
      let bChange = bRating?.change ?? null;

      if (aChange === null || bChange === null) {
        if (m.winner === "a") {
          aChange = 15;
          bChange = -15;
        } else if (m.winner === "b") {
          aChange = -15;
          bChange = 15;
        } else {
          aChange = 0;
          bChange = 0;
        }
      }
      
      let winnerName: string | null = null;
      if (m.winner === "a") winnerName = teamAName;
      else if (m.winner === "b") winnerName = teamBName;

      const createdDate = m.createdAt ? new Date(m.createdAt) : new Date();
      const finishedDate = m.finishedAt ? new Date(m.finishedAt) : null;

      return {
        id: m.id,
        seed: m.seed || 927316646,
        kind: m.kind,
        teamA: teamAName,
        teamB: teamBName,
        teamAImage,
        teamBImage,
        teamARating: aRating?.rating ?? 600,
        teamBRating: bRating?.rating ?? 600,
        teamAChange: aChange,
        teamBChange: bChange,
        winner: m.winner,
        winnerName,
        scores: Array.isArray(m.scores) ? m.scores : [],
        createdAt: createdDate.toISOString(),
        finishedAt: finishedDate ? finishedDate.toISOString() : null,
        submissionAId: m.submissionAId,
        submissionBId: m.submissionBId,
      };
    });

    return NextResponse.json(formattedMatches);
  } catch (error) {
    console.error("Replays GET error:", error);
    return NextResponse.json([]);
  }
}
