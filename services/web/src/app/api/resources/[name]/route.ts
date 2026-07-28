import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const DOCS_DIR = path.join(process.cwd(), "public", "docs");

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name } = await params;

  const allowed = new Set(["README.md", "agents.md", "main.py"]);
  if (!allowed.has(name)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const filePath = path.join(DOCS_DIR, name);
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const mime =
      name.endsWith(".md") ? "text/markdown" : "text/x-python";
    return new NextResponse(content, {
      headers: {
        "Content-Type": mime,
        "Content-Disposition": `attachment; filename="${name}"`,
        "Content-Length": String(Buffer.byteLength(content, "utf-8")),
      },
    });
  } catch {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
}
