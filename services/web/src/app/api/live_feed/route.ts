import { NextResponse } from "next/server";
import { getS3, S3_BUCKET, GetObjectCommand } from "@/lib/s3";

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const s3 = getS3();
    if (!s3) {
       return NextResponse.json({ events: [] });
    }
    const command = new GetObjectCommand({
      Bucket: S3_BUCKET,
      Key: "live_feed.json",
    });
    
    const data = await s3.send(command);
    
    if (!data.Body) {
      return NextResponse.json({ events: [] });
    }
    
    const text = await data.Body.transformToString("utf-8");
    const json = JSON.parse(text);
    return NextResponse.json(json);
  } catch (error: any) {
    if (error.name === 'NoSuchKey' || error.Code === 'NoSuchKey') {
      return NextResponse.json({ events: [] });
    }
    console.error("Error fetching live feed:", error);
    return NextResponse.json({ error: "Failed to fetch live feed" }, { status: 500 });
  }
}
