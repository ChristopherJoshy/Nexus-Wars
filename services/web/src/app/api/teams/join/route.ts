import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { teams, teamMembers } from "@/lib/db/schema";
import { getSession } from "@/lib/get-session";
import { eq } from "drizzle-orm";

export async function POST(req: NextRequest) {
  const session = await getSession(req);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { teamCode } = await req.json();
  if (!teamCode || typeof teamCode !== "string" || teamCode.length !== 6) {
    return NextResponse.json({ error: "Invalid team code" }, { status: 400 });
  }

  const code = teamCode.toUpperCase();
  if (!/^[A-Z0-9]{6}$/.test(code)) {
    return NextResponse.json({ error: "Invalid team code" }, { status: 400 });
  }

  try {
    const existing = await db.query.teamMembers.findFirst({
      where: eq(teamMembers.userId, session.user.id),
    });
    if (existing) {
      return NextResponse.json({ error: "Already on a team" }, { status: 409 });
    }

    const team = await db.query.teams.findFirst({
      where: eq(teams.teamCode, code),
    });
    if (!team) {
      return NextResponse.json({ error: "Team not found" }, { status: 404 });
    }

    await db.insert(teamMembers).values({
      teamId: team.id,
      userId: session.user.id,
      role: "member",
    });

    return NextResponse.json({
      ...team,
      team_code: team.teamCode,
      owner_id: team.ownerId,
      created_at: team.createdAt,
    });
  } catch (error: unknown) {
    console.error("Error joining team:", error);
    return NextResponse.json({ error: "Failed to join team" }, { status: 500 });
  }
}
