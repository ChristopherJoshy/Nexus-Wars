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

  return NextResponse.json({
    submissionsPaused: paused,
    adminEmail: admin.user.email,
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
