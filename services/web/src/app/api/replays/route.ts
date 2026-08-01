import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { matches, teams, matchParticipants, submissions } from "@/lib/db/schema";
import { eq, or, and, desc, inArray } from "drizzle-orm";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const teamIdParam = searchParams.get("teamId");
  const submissionId = searchParams.get("submissionId");

  try {
    let effectiveTeamId = teamIdParam;
    if (!effectiveTeamId && submissionId) {
      const sub = await db.query.submissions.findFirst({
        where: eq(submissions.id, submissionId),
      });
      if (sub?.teamId) {
        effectiveTeamId = sub.teamId;
      }
    }

    const baseWhere = eq(matches.status, "finished");

    // Prioritize teamId filtering over submissionId when both are provided
    // (e.g. from leaderboard links that pass both). This ensures all team
    // matches are shown, not just the ones for a specific submission.
    const teamOrSubmissionWhere = effectiveTeamId
      ? or(eq(matches.teamAId, effectiveTeamId), eq(matches.teamBId, effectiveTeamId))
      : submissionId
        ? or(eq(matches.submissionAId, submissionId), eq(matches.submissionBId, submissionId))
        : undefined;

    const whereClause = teamOrSubmissionWhere
      ? and(baseWhere, teamOrSubmissionWhere)
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

    const allTeams = await db.select({ id: teams.id, name: teams.name }).from(teams);
    const teamMap = new Map(allTeams.map((t) => [t.id, t.name]));

    const matchIds = recentMatches.map((m) => m.id);
    const allParticipants = matchIds.length > 0
      ? await db
          .select()
          .from(matchParticipants)
          .where(inArray(matchParticipants.matchId, matchIds))
      : [];
    const ratingMap = new Map<string, { rating: number; rd: number; change: number | null }>();
    for (const p of allParticipants) {
      const key = `${p.matchId}:${p.teamId}`;
      const change = p.ratingAfter != null && p.ratingBefore != null
        ? Math.round(p.ratingAfter - p.ratingBefore)
        : null;
      ratingMap.set(key, {
        rating: p.ratingAfter ?? p.ratingBefore ?? 600,
        rd: p.rdAfter ?? p.rdBefore ?? 350,
        change,
      });
    }

    const formattedMatches = recentMatches.map((m) => {
      const teamAName = (m.teamAId && teamMap.get(m.teamAId)) || "Team Alpha";
      const teamBName = (m.teamBId && teamMap.get(m.teamBId)) || "Team Beta";

      const aRating = m.teamAId ? ratingMap.get(`${m.id}:${m.teamAId}`) : null;
      const bRating = m.teamBId ? ratingMap.get(`${m.id}:${m.teamBId}`) : null;

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
