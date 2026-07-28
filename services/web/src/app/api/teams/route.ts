import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { teams, teamMembers, ratings, users } from "@/lib/db/schema";
import { getSession } from "@/lib/get-session";
import { eq } from "drizzle-orm";

function generateTeamCode(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from(
    { length: 6 },
    () => chars[Math.floor(Math.random() * chars.length)]
  ).join("");
}

function sanitizeName(name: unknown): string | null {
  if (typeof name !== "string") return null;
  const trimmed = name.trim();
  if (trimmed.length < 2 || trimmed.length > 32) return null;
  if (!/^[a-zA-Z0-9]+[a-zA-Z0-9 _-]*[a-zA-Z0-9]+$|^[a-zA-Z0-9]{2,32}$/.test(trimmed))
    return null;
  return trimmed;
}

export async function POST(req: NextRequest) {
  const session = await getSession(req);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { name: rawName } = await req.json();
  const name = sanitizeName(rawName);
  if (!name) {
    return NextResponse.json(
      { error: "Team name must be 2-32 chars (alphanumeric, spaces, hyphens, underscores)" },
      { status: 400 }
    );
  }

  try {
    const [team] = await db.transaction(async (tx) => {
      const existing = await tx.query.teamMembers.findFirst({
        where: eq(teamMembers.userId, session.user.id),
      });
      if (existing) {
        tx.rollback();
        return [];
      }

      const [t] = await tx
        .insert(teams)
        .values({
          name,
          teamCode: generateTeamCode(),
          ownerId: session.user.id,
        })
        .returning();

      await tx.insert(teamMembers).values({
        teamId: t.id,
        userId: session.user.id,
        role: "owner",
      });

      await tx.insert(ratings).values({ teamId: t.id });

      return [t];
    });

    if (!team) {
      return NextResponse.json({ error: "Already on a team" }, { status: 409 });
    }

    return NextResponse.json({
      ...team,
      team_code: team.teamCode,
      owner_id: team.ownerId,
      created_at: team.createdAt,
    });
  } catch (error: unknown) {
    if (error instanceof Error && error.message === "Already on a team") {
      return NextResponse.json({ error: "Already on a team" }, { status: 409 });
    }
    throw error;
  }
}

export async function GET(req: NextRequest) {
  const session = await getSession(req);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const membership = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
  });
  if (!membership) {
    return NextResponse.json({ error: "No team" }, { status: 404 });
  }

  const [team] = await db
    .select({
      id: teams.id,
      name: teams.name,
      teamCode: teams.teamCode,
      team_code: teams.teamCode,
      ownerId: teams.ownerId,
      owner_id: teams.ownerId,
      createdAt: teams.createdAt,
      created_at: teams.createdAt,
    })
    .from(teams)
    .where(eq(teams.id, membership.teamId))
    .limit(1);

  if (!team) {
    return NextResponse.json({ error: "No team" }, { status: 404 });
  }

  const members = await db
    .select({
      userId: teamMembers.userId,
      role: teamMembers.role,
      joinedAt: teamMembers.joinedAt,
      name: users.name,
      email: users.email,
      image: users.image,
    })
    .from(teamMembers)
    .innerJoin(users, eq(teamMembers.userId, users.id))
    .where(eq(teamMembers.teamId, team.id));

  return NextResponse.json({ ...team, members });
}
