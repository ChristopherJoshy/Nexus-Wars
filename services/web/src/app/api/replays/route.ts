import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { matches, teams, matchParticipants } from "@/lib/db/schema";
import { eq, or, and, desc, inArray } from "drizzle-orm";

function formatRelativeTime(dateInput: Date | string | null | undefined): string {
  if (!dateInput) return "Just now";
  const date = typeof dateInput === "string" ? new Date(dateInput) : dateInput;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  if (diffSecs < 60) return "Just now";
  const diffMins = Math.floor(diffSecs / 60);
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths}mo ago`;
  const diffYears = Math.floor(diffDays / 365);
  return `${diffYears}y ago`;
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const teamId = searchParams.get("teamId");
  const submissionId = searchParams.get("submissionId");

    try {
    const baseWhere = eq(matches.status, "finished");
    const teamOrSubmissionWhere = teamId
      ? or(eq(matches.teamAId, teamId), eq(matches.teamBId, teamId))
      : submissionId
        ? or(eq(matches.submissionAId, submissionId), eq(matches.submissionBId, submissionId))
        : undefined;

    const whereClause = teamOrSubmissionWhere
      ? and(baseWhere, teamOrSubmissionWhere)
      : baseWhere;

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
      .orderBy(desc(matches.createdAt))
      .limit(30);

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
        relativeTime: formatRelativeTime(createdDate),
      };
    });

    return NextResponse.json(formattedMatches);
  } catch (error) {
    console.error("Replays GET error:", error);
    return NextResponse.json([]);
  }
}
