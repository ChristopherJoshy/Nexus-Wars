import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const DOCS_DIR = path.join(process.cwd(), "public", "docs");

export async function GET() {
  const files = ["README.md", "agents.md", "main.py"];
  const result = [];

  for (const name of files) {
    const filePath = path.join(DOCS_DIR, name);
    try {
      const stat = fs.statSync(filePath);
      result.push({
        name,
        sizeBytes: stat.size,
        size: `${(stat.size / 1024).toFixed(1)} kB`,
        mime: name.endsWith(".md") ? "text/markdown" : "text/x-python",
      });
    } catch {
      result.push({ name, sizeBytes: 0, size: "", mime: "text/plain" });
    }
  }

  return NextResponse.json(result);
}
