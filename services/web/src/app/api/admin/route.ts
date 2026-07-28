import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { settings } from "@/lib/db/schema";
import { getSession } from "@/lib/get-session";
import { eq } from "drizzle-orm";

const ADMIN_EMAIL = "christopherjoshy4@gmail.com";

async function requireAdmin(req: NextRequest) {
  const session = await getSession(req);
  if (!session?.user || session.user.email !== ADMIN_EMAIL) {
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
  const paused = row?.value === "true" || row?.value === true;

  return NextResponse.json({
    submissionsPaused: paused,
    adminEmail: ADMIN_EMAIL,
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

  await db
    .insert(settings)
    .values({
      key: "submissions_paused",
      value: submissionsPaused ? "true" : "false",
      updatedAt: new Date(),
    })
    .onConflictDoUpdate({
      target: settings.key,
      set: { value: submissionsPaused ? "true" : "false", updatedAt: new Date() },
    });

  return NextResponse.json({ submissionsPaused });
}
