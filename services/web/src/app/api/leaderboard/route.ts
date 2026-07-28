import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { submissionRatings, teams, teamMembers, users, submissions } from "@/lib/db/schema";
import { eq, desc, sql } from "drizzle-orm";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    // 1. Fetch each team's highest-rated submission
    const topSubs = await db
      .select({
        teamId: submissionRatings.teamId,
        teamName: teams.name,
        rating: submissionRatings.rating,
        rd: submissionRatings.rd,
        wins: submissionRatings.wins,
        losses: submissionRatings.losses,
        draws: submissionRatings.draws,
        matchesPlayed: submissionRatings.matchesPlayed,
        lastMatchAt: submissionRatings.lastMatchAt,
        bestSubmissionId: submissionRatings.submissionId,
      })
      .from(submissionRatings)
      .innerJoin(teams, eq(submissionRatings.teamId, teams.id))
      .orderBy(submissionRatings.teamId, desc(submissionRatings.rating));

    // distinct on team_id keeps highest rating per team
    // drizzle doesn't have DISTINCT ON, so we deduplicate in JS
    const boardMap = new Map<string, typeof topSubs[0]>();
    for (const row of topSubs) {
      if (!row.teamId) continue;
      if (!boardMap.has(row.teamId)) {
        boardMap.set(row.teamId, row);
      }
    }
    const board = Array.from(boardMap.values()).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));

    // 2. Fetch team members
    const teamIds = board.map((b) => b.teamId);
    let membersByTeam: Record<string, { name: string; image: string | null }[]> = {};

    if (teamIds.length > 0) {
      const allMembers = await db
        .select({
          teamId: teamMembers.teamId,
          name: users.name,
          image: users.image,
        })
        .from(teamMembers)
        .innerJoin(users, eq(teamMembers.userId, users.id));

      membersByTeam = allMembers.reduce((acc, m) => {
        if (!acc[m.teamId]) acc[m.teamId] = [];
        acc[m.teamId].push({
          name: m.name || "Member",
          image: m.image || null,
        });
        return acc;
      }, {} as Record<string, { name: string; image: string | null }[]>);
    }

    // 3. Format result
    const result = board.map((b) => {
      const teamId = b.teamId ?? "";
      return {
        teamId: b.teamId,
        teamName: b.teamName,
        rating: Math.round((b.rating ?? 600) * 10) / 10,
        rd: Math.round((b.rd ?? 350) * 10) / 10,
        wins: b.wins ?? 0,
        losses: b.losses ?? 0,
        draws: b.draws ?? 0,
        matchesPlayed: b.matchesPlayed ?? 0,
        lastActivityAt: b.lastMatchAt || undefined,
        bestSubmissionId: b.bestSubmissionId,
        members: teamId ? (membersByTeam[teamId] || [{ name: b.teamName, image: null }]) : [{ name: b.teamName, image: null }],
      };
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error("Leaderboard GET error:", error);
    return NextResponse.json([]);
  }
}
