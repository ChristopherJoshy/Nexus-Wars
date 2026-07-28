import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { ratings, teams, teamMembers, users } from "@/lib/db/schema";
import { eq, desc } from "drizzle-orm";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    // 1. Fetch top rated teams
    const board = await db
      .select({
        teamId: ratings.teamId,
        teamName: teams.name,
        rating: ratings.rating,
        rd: ratings.rd,
        wins: ratings.wins,
        losses: ratings.losses,
        draws: ratings.draws,
        matchesPlayed: ratings.matchesPlayed,
        lastMatchAt: ratings.lastMatchAt,
        teamCreatedAt: teams.createdAt,
      })
      .from(ratings)
      .innerJoin(teams, eq(ratings.teamId, teams.id))
      .orderBy(desc(ratings.rating))
      .limit(100);

    // 2. Fetch team members with Google profile images for all teams on the leaderboard
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

    // 3. Format result with members and real timestamps
    const result = board.map((b) => ({
      teamId: b.teamId,
      teamName: b.teamName,
      rating: Math.round(b.rating * 10) / 10,
      rd: Math.round(b.rd * 10) / 10,
      wins: b.wins,
      losses: b.losses,
      draws: b.draws,
      matchesPlayed: b.matchesPlayed,
      lastActivityAt: b.lastMatchAt || b.teamCreatedAt,
      members: membersByTeam[b.teamId] || [{ name: b.teamName, image: null }],
    }));

    return NextResponse.json(result);
  } catch (error) {
    console.error("Leaderboard GET error:", error);
    return NextResponse.json([]);
  }
}
