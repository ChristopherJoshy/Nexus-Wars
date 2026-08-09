import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { settings } from "@/lib/db/schema";
import { getSession } from "@/lib/get-session";
import { eq } from "drizzle-orm";

const DEFAULT_ADMIN_EMAIL = "christopherjoshy4@gmail.com";

function getAdminEmails(): string[] {
  const env = process.env.ADMIN_EMAILS || "";
  const list = env.split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
  if (!list.includes(DEFAULT_ADMIN_EMAIL.toLowerCase())) {
    list.push(DEFAULT_ADMIN_EMAIL.toLowerCase());
  }
  return list;
}

export function parsePausedValue(val: unknown): boolean {
  if (val === true || val === "true") return true;
  if (typeof val === "string" && val.replace(/"/g, "").trim().toLowerCase() === "true") return true;
  return false;
}

async function requireAdmin(req: NextRequest) {
  const session = await getSession(req);
  if (!session?.user?.email) {
    return null;
  }
  const userEmail = session.user.email.toLowerCase();
  const allowed = getAdminEmails();
  if (!allowed.includes(userEmail)) {
    return null;
  }
  return session;
}

export async function GET(req: NextRequest) {
  const admin = await requireAdmin(req);
  if (!admin) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const row = await db.query.settings.findFirst({
    where: eq(settings.key, "submissions_paused"),
  });
  const paused = parsePausedValue(row?.value);

  // Fetch all registered teams with rating and contact info
  const allTeams = await db.execute<{
    id: string;
    name: string;
    college_name: string | null;
    team_members_info: string | null;
    mobile_numbers: string | null;
    rating: number | null;
    created_at: string;
  }>(`
    SELECT t.id, t.name, t.college_name, t.team_members_info, t.mobile_numbers,
           COALESCE(r.rating, 600.0) as rating, t.created_at
    FROM teams t
    LEFT JOIN ratings r ON t.id = r.team_id
    ORDER BY r.rating DESC NULLS LAST;
  `);

  const formattedTeams = (Array.isArray(allTeams) ? allTeams : []).map((t, idx) => ({
    id: t.id,
    rank: idx + 1,
    name: t.name,
    collegeName: t.college_name || "N/A",
    teamMembersInfo: t.team_members_info || "N/A",
    mobileNumbers: t.mobile_numbers || "N/A",
    rating: typeof t.rating === "number" ? Math.round(t.rating * 100) / 100 : 600.0,
    createdAt: t.created_at,
  }));

  return NextResponse.json({
    submissionsPaused: paused,
    adminEmail: admin.user.email,
    teams: formattedTeams,
  });
}

export async function POST(req: NextRequest) {
  const admin = await requireAdmin(req);
  if (!admin) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { submissionsPaused } = await req.json();
  if (typeof submissionsPaused !== "boolean") {
    return NextResponse.json({ error: "submissionsPaused must be boolean" }, { status: 400 });
  }

  const strVal = submissionsPaused ? "true" : "false";

  await db
    .insert(settings)
    .values({
      key: "submissions_paused",
      value: strVal,
      updatedAt: new Date(),
    })
    .onConflictDoUpdate({
      target: settings.key,
      set: { value: strVal, updatedAt: new Date() },
    });

  return NextResponse.json({ submissionsPaused });
}
