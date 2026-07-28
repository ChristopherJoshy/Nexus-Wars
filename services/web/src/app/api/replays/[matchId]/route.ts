import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { matches, teamMembers } from "@/lib/db/schema";
import { getSession } from "@/lib/get-session";
import { eq } from "drizzle-orm";
import { getS3, S3_BUCKET, GetObjectCommand } from "@/lib/s3";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ matchId: string }> }
) {
  const { matchId } = await params;

  const match = await db.query.matches.findFirst({
    where: eq(matches.id, matchId),
  });
  if (!match) {
    return NextResponse.json({ error: "Match not found" }, { status: 404 });
  }

  // Secure validation replays: only participating team members can view them.
  if (match.kind === "validation") {
    const session = await getSession(req);
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    const membership = await db.query.teamMembers.findFirst({
      where: eq(teamMembers.userId, session.user.id),
    });
    if (
      !membership ||
      (membership.teamId !== match.teamAId && membership.teamId !== match.teamBId)
    ) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }
  }

  if (!match.replayKey) {
    return NextResponse.json(
      { error: "Replay not available" },
      { status: 404 }
    );
  }

  const s3 = getS3();
  if (!s3) {
    return NextResponse.json(
      { error: "Storage not configured" },
      { status: 500 }
    );
  }

  try {
    const result = await s3.send(
      new GetObjectCommand({
        Bucket: S3_BUCKET,
        Key: match.replayKey,
      })
    );
    const body = await result.Body?.transformToString();
    if (!body) {
      return NextResponse.json(
        { error: "Replay data empty" },
        { status: 404 }
      );
    }
    const replay = JSON.parse(body);
    return NextResponse.json(replay);
  } catch {
    return NextResponse.json(
      { error: "Replay not found in storage" },
      { status: 404 }
    );
  }
}
