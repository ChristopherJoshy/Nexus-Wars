import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/get-session";
import { db } from "@/lib/db";
import { submissions, teamMembers } from "@/lib/db/schema";
import { eq } from "drizzle-orm";
import { getS3, S3_BUCKET } from "@/lib/s3";
import { GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getSession(req);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;

  // Verify the user is in a team
  const membership = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
  });
  if (!membership) {
    return NextResponse.json({ error: "No team" }, { status: 400 });
  }

  // Fetch the submission and verify it belongs to this team
  const submission = await db.query.submissions.findFirst({
    where: eq(submissions.id, id),
  });

  if (!submission) {
    return NextResponse.json({ error: "Submission not found" }, { status: 404 });
  }

  if (submission.teamId !== membership.teamId) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const artifactKey = submission.artifactKey;
  if (!artifactKey) {
    return NextResponse.json({ error: "No artifact available" }, { status: 404 });
  }

  const s3 = getS3();
  if (!s3) {
    return NextResponse.json({ error: "Storage not configured" }, { status: 503 });
  }

  // Extract filename from the artifact key
  const filename = artifactKey.split("/").pop() || "agent.py";

  // Generate a presigned URL valid for 60 seconds
  const command = new GetObjectCommand({
    Bucket: S3_BUCKET,
    Key: artifactKey,
    ResponseContentDisposition: `attachment; filename="${filename}"`,
    ResponseContentType: "text/plain",
  });

  const url = await getSignedUrl(s3, command, { expiresIn: 60 });

  return NextResponse.json({ url, filename });
}
