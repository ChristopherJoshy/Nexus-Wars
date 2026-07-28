import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { competitions } from "@/lib/db/schema";
import { eq } from "drizzle-orm";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const comp = await db.query.competitions.findFirst({
      where: eq(competitions.slug, "nexus-wars"),
    });
    if (!comp) {
      return NextResponse.json({
        slug: "nexus-wars",
        title: "Nexus Wars",
        status: "open",
      });
    }
    return NextResponse.json({
      slug: comp.slug,
      title: comp.title,
      status: comp.status,
    });
  } catch {
    return NextResponse.json({
      slug: "nexus-wars",
      title: "Nexus Wars",
      status: "open",
    });
  }
}
