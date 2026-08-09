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

async function getFullTeamForUser(userId: string) {
  const membership = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, userId),
  });
  if (!membership) return null;

  const [team] = await db
    .select({
      id: teams.id,
      name: teams.name,
      teamCode: teams.teamCode,
      team_code: teams.teamCode,
      ownerId: teams.ownerId,
      owner_id: teams.ownerId,
      collegeName: teams.collegeName,
      teamMembersInfo: teams.teamMembersInfo,
      mobileNumbers: teams.mobileNumbers,
      createdAt: teams.createdAt,
      created_at: teams.createdAt,
    })
    .from(teams)
    .where(eq(teams.id, membership.teamId))
    .limit(1);

  if (!team) return null;

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

  return { ...team, members };
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
    const existing = await db.query.teamMembers.findFirst({
      where: eq(teamMembers.userId, session.user.id),
    });

    if (existing) {
      if (existing.role !== "owner") {
        return NextResponse.json(
          { error: "Only team leaders can edit the team name" },
          { status: 403 }
        );
      }

      // User is owner -> Update existing team name
      await db
        .update(teams)
        .set({ name })
        .where(eq(teams.id, existing.teamId));

      const updatedTeam = await getFullTeamForUser(session.user.id);
      return NextResponse.json(updatedTeam);
    }

    // User is NOT on a team -> Create a new team
    const team = await db.transaction(async (tx) => {
      let t: typeof teams.$inferSelect | undefined;
      for (let attempt = 0; attempt < 5; attempt++) {
        try {
          const [inserted] = await tx
            .insert(teams)
            .values({
              name,
              teamCode: generateTeamCode(),
              ownerId: session.user.id,
            })
            .returning();
          t = inserted;
          break;
        } catch (e: unknown) {
          if (
            typeof e === "object" &&
            e !== null &&
            "code" in e &&
            (e as { code: string }).code === "23505" &&
            attempt < 4
          ) {
            continue;
          }
          throw e;
        }
      }

      if (!t) {
        throw new Error("Failed to generate unique team code");
      }

      await tx.insert(teamMembers).values({
        teamId: t.id,
        userId: session.user.id,
        role: "owner",
      });

      await tx.insert(ratings).values({ teamId: t.id });

      return t;
    });

    const fullTeam = await getFullTeamForUser(session.user.id);
    return NextResponse.json(fullTeam || team);
  } catch (error: unknown) {
    console.error("Error saving team:", error);
    return NextResponse.json({ error: "Failed to save team settings" }, { status: 500 });
  }
}

export async function PATCH(req: NextRequest) {
  const session = await getSession(req);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const { name: rawName, collegeName, teamMembersInfo, mobileNumbers, teamId: requestedTeamId } = body;

  const existing = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
  });

  const targetTeamId = requestedTeamId || existing?.teamId;

  if (!targetTeamId) {
    return NextResponse.json({ error: "No team found" }, { status: 404 });
  }

  // Update fields
  const updateData: Partial<typeof teams.$inferInsert> = {};

  if (rawName !== undefined) {
    const name = sanitizeName(rawName);
    if (!name) {
      return NextResponse.json(
        { error: "Team name must be 2-32 chars (alphanumeric, spaces, hyphens, underscores)" },
        { status: 400 }
      );
    }
    updateData.name = name;
  }

  if (collegeName !== undefined) updateData.collegeName = String(collegeName).trim();
  if (teamMembersInfo !== undefined) updateData.teamMembersInfo = String(teamMembersInfo).trim();
  if (mobileNumbers !== undefined) updateData.mobileNumbers = String(mobileNumbers).trim();

  if (Object.keys(updateData).length > 0) {
    await db
      .update(teams)
      .set(updateData)
      .where(eq(teams.id, targetTeamId));
  }

  const updatedTeam = await getFullTeamForUser(session.user.id);
  return NextResponse.json(updatedTeam);
}

export async function GET(req: NextRequest) {
  const session = await getSession(req);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const team = await getFullTeamForUser(session.user.id);
  if (!team) {
    return NextResponse.json({ error: "No team" }, { status: 404 });
  }

  return NextResponse.json(team);
}
