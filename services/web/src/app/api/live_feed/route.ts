import { NextResponse } from "next/server";
import { getS3, S3_BUCKET } from "@/lib/s3";
import { GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const s3 = getS3();
    if (!s3) {
      return NextResponse.json({ events: [] });
    }

    // Return a short-lived presigned URL so the browser fetches directly
    // from MinIO — bypasses Vercel origin transfer entirely.
    const command = new GetObjectCommand({
      Bucket: S3_BUCKET,
      Key: "live_feed.json",
      ResponseContentType: "application/json",
    });

    const url = await getSignedUrl(s3, command, { expiresIn: 30 });
    return NextResponse.json({ url });
  } catch (error: any) {
    if (error.name === 'NoSuchKey' || error.Code === 'NoSuchKey') {
      return NextResponse.json({ events: [] });
    }
    console.error("Error generating live feed URL:", error);
    return NextResponse.json({ error: "Failed to fetch live feed" }, { status: 500 });
  }
}
