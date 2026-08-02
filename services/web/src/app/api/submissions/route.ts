import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { submissions, teamMembers, jobs, settings, submissionRatings, teams, users } from "@/lib/db/schema";
import { getSession } from "@/lib/get-session";
import { eq, ne, sql, and, gte } from "drizzle-orm";
import { getS3, S3_BUCKET, PutObjectCommand } from "@/lib/s3";
import { randomUUID } from "crypto";
import { parsePausedValue } from "@/app/api/admin/route";

const MAX_SUBMISSIONS_PER_DAY = 10;

function getTodayStartUTC(): Date {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0));
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
    return NextResponse.json({
      submissions: [],
      totalCount: 0,
      maxSubmissions: MAX_SUBMISSIONS_PER_DAY,
      submissionsPaused: false,
    });
  }

  const team = await db.query.teams.findFirst({
    where: eq(teams.id, membership.teamId),
  });

  const subs = await db.query.submissions.findMany({
    where: eq(submissions.teamId, membership.teamId),
    orderBy: (subs, { desc }) => [desc(subs.createdAt)],
    limit: 50,
  });

  const ratingsRows = await db
    .select({
      submissionId: submissionRatings.submissionId,
      rating: submissionRatings.rating,
      rd: submissionRatings.rd,
      wins: submissionRatings.wins,
      losses: submissionRatings.losses,
      draws: submissionRatings.draws,
      matchesPlayed: submissionRatings.matchesPlayed,
    })
    .from(submissionRatings)
    .innerJoin(submissions, eq(submissionRatings.submissionId, submissions.id))
    .where(eq(submissions.teamId, membership.teamId));

  const ratingMap = new Map(
    ratingsRows.map((r) => [r.submissionId, r])
  );

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

  const pausedRow = await db.query.settings.findFirst({
    where: eq(settings.key, "submissions_paused"),
  });
  const submissionsPaused = parsePausedValue(pausedRow?.value);

  const enriched = subs.map((s) => {
    const r = ratingMap.get(s.id) || null;
    const filename = (s.artifactKey || "agent.py").split("/").pop() || "agent.py";
    return {
      ...s,
      filename,
      rating: r?.rating ?? null,
      rd: r?.rd ?? null,
      wins: r?.wins ?? 0,
      losses: r?.losses ?? 0,
      draws: r?.draws ?? 0,
      matchesPlayed: r?.matchesPlayed ?? 0,
    };
  });

  return NextResponse.json({
    submissions: enriched,
    totalCount: countResult?.count ?? 0,
    maxSubmissions: MAX_SUBMISSIONS_PER_DAY,
    submissionsPaused,
  });
}
