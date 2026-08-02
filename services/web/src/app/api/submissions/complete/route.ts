import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { submissions, teamMembers, jobs } from "@/lib/db/schema";
import { getSession } from "@/lib/get-session";
import { eq } from "drizzle-orm";

export async function POST(req: NextRequest) {
  const session = await getSession(req);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const membership = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
  });
  if (!membership) {
    return NextResponse.json({ error: "No team" }, { status: 400 });
  }

  let body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { subId, artifactKey } = body;
  if (!subId || !artifactKey) {
    return NextResponse.json({ error: "Missing subId or artifactKey" }, { status: 400 });
  }

  // Double check that the artifactKey belongs to this team (security check)
  if (!artifactKey.startsWith(`submissions/${membership.teamId}/`)) {
    return NextResponse.json({ error: "Invalid artifact path" }, { status: 403 });
  }

  // Verify submission doesn't already exist
  const existing = await db.query.submissions.findFirst({
    where: eq(submissions.id, subId),
  });
  if (existing) {
    return NextResponse.json({ error: "Submission already completed" }, { status: 400 });
  }

  const [sub] = await db
    .insert(submissions)
    .values({
      id: subId,
      teamId: membership.teamId,
      userId: session.user.id,
      status: "queued",
      artifactKey,
      engineVersion: "2026.1.0",
    })
    .returning();

  await db.insert(jobs).values({
    type: "validate",
    payloadJson: { submission_id: subId },
    status: "pending",
  });

  return NextResponse.json(sub);
}
