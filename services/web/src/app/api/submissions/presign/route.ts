import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { submissions, teamMembers, settings } from "@/lib/db/schema";
import { getSession } from "@/lib/get-session";
import { eq, ne, sql, and, gte } from "drizzle-orm";
import { getS3, S3_BUCKET } from "@/lib/s3";
import { randomUUID } from "crypto";
import { parsePausedValue } from "@/app/api/admin/route";
import { createPresignedPost } from "@aws-sdk/s3-presigned-post";

const MAX_SUBMISSIONS_PER_DAY = 10;
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

function getTodayStartUTC(): Date {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0));
}

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

  const pausedRow = await db.query.settings.findFirst({
    where: eq(settings.key, "submissions_paused"),
  });
  if (pausedRow && parsePausedValue(pausedRow.value)) {
    return NextResponse.json(
      { error: "Submissions are currently paused by the admin." },
      { status: 503 }
    );
  }

  const todayStart = getTodayStartUTC();
  const [countResult] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(submissions)
    .where(
      and(
        eq(submissions.teamId, membership.teamId),
        gte(submissions.createdAt, todayStart),
        ne(submissions.status, "rejected")
      )
    );

  if ((countResult?.count ?? 0) >= MAX_SUBMISSIONS_PER_DAY) {
    return NextResponse.json(
      {
        error: `Maximum of ${MAX_SUBMISSIONS_PER_DAY} submissions per team per day reached. Try again tomorrow.`,
        code: "SUBMISSION_LIMIT",
      },
      { status: 429 }
    );
  }

  let filename = "agent.py";
  try {
    const body = await req.json();
    if (body.filename && body.filename.endsWith(".py")) {
      filename = body.filename;
    }
  } catch {
    // Ignore body parsing errors
  }

  const subId = randomUUID();
  const artifactKey = `submissions/${membership.teamId}/${subId}/${filename}`;

  const s3 = getS3();
  if (!s3) {
    return NextResponse.json({ error: "S3 configuration error" }, { status: 500 });
  }

  try {
    // Generate a presigned POST policy with strict limits to prevent abuse
    const { url, fields } = await createPresignedPost(s3, {
      Bucket: S3_BUCKET,
      Key: artifactKey,
      Conditions: [
        ["content-length-range", 0, MAX_FILE_SIZE_BYTES], // Strictly limit file size at MinIO layer (10MB max)
      ],
      Fields: {
        success_action_status: "201",
        "Content-Type": "text/x-python"
      },
      Expires: 300, // Valid for 5 minutes
    });

    return NextResponse.json({
      url,
      fields,
      subId,
      artifactKey
    });
  } catch (err) {
    console.error("Presign error:", err);
    return NextResponse.json({ error: "Failed to generate upload URL" }, { status: 500 });
  }
}
