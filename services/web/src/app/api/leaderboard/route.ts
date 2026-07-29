import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { submissionRatings, teams, teamMembers, users, submissions } from "@/lib/db/schema";
import { eq, desc } from "drizzle-orm";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const allTeams = await db
      .select({
        teamId: teams.id,
        teamName: teams.name,
      })
      .from(teams);

    const topSubs = await db
      .select({
        teamId: submissionRatings.teamId,
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
      .orderBy(submissionRatings.teamId, desc(submissionRatings.rating));

    const bestByTeam = new Map<string, typeof topSubs[0]>();
    for (const row of topSubs) {
      if (!row.teamId) continue;
      if (!bestByTeam.has(row.teamId)) bestByTeam.set(row.teamId, row);
    }

    const latestSubmissions = await db
      .select({
        teamId: submissions.teamId,
        createdAt: submissions.createdAt,
      })
      .from(submissions)
      .orderBy(submissions.teamId, desc(submissions.createdAt));

    const lastSubByTeam = new Map<string, Date>();
    for (const sub of latestSubmissions) {
      if (sub.teamId && sub.createdAt && !lastSubByTeam.has(sub.teamId)) {
        lastSubByTeam.set(sub.teamId, sub.createdAt);
      }
    }

    const teamIds = allTeams.map((t) => t.teamId);
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

    const result = allTeams
      .map((t) => {
        const top = bestByTeam.get(t.teamId);
        const teamId = t.teamId ?? "";
        const lastSubAt = t.teamId ? lastSubByTeam.get(t.teamId) : null;
        const lastActivityAt = lastSubAt
          ? lastSubAt.toISOString()
          : (top?.lastMatchAt ? top.lastMatchAt.toISOString() : undefined);

        return {
          teamId: t.teamId,
          teamName: t.teamName,
          rating: Math.round((top?.rating ?? 600) * 10) / 10,
          rd: Math.round((top?.rd ?? 350) * 10) / 10,
          wins: top?.wins ?? 0,
          losses: top?.losses ?? 0,
          draws: top?.draws ?? 0,
          matchesPlayed: top?.matchesPlayed ?? 0,
          lastActivityAt,
          bestSubmissionId: top?.bestSubmissionId || undefined,
          members: teamId ? (membersByTeam[teamId] || [{ name: t.teamName, image: null }]) : [{ name: t.teamName, image: null }],
        };
      })
      .sort((a, b) => (b.rating ?? 600) - (a.rating ?? 600));

    return NextResponse.json(result);
  } catch (error) {
    console.error("Leaderboard GET error:", error);
    return NextResponse.json([]);
  }
}
