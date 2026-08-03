import { NextResponse } from "next/server";
import { s3, S3_BUCKET } from "@/lib/s3";

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const data = await s3.getObject({
      Bucket: S3_BUCKET,
      Key: "live_feed.json",
    });
    
    if (!data.Body) {
      return NextResponse.json({ events: [] });
    }
    
    const text = await data.Body.transformToString("utf-8");
    const json = JSON.parse(text);
    return NextResponse.json(json);
  } catch (error: any) {
    if (error.name === 'NoSuchKey') {
      return NextResponse.json({ events: [] });
    }
    console.error("Error fetching live feed:", error);
    return NextResponse.json({ error: "Failed to fetch live feed" }, { status: 500 });
  }
}
