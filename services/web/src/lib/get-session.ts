import { NextRequest } from "next/server";
import { getAuth } from "firebase-admin/auth";
import { firebaseAdmin } from "./firebase-admin";
import { db } from "./db";
import { users } from "./db/schema";
import { eq } from "drizzle-orm";

export async function getSession(req: NextRequest) {
  const authHeader = req.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    if (process.env.NODE_ENV === "development") {
      console.error("[getSession] No Bearer token. Header:", authHeader ?? "(missing)");
    }
    return null;
  }

  const token = authHeader.slice(7);
  if (process.env.NODE_ENV === "development") {
    console.log("[getSession] Token length:", token.length, "starts:", token.substring(0, 20) + "...");
  }
  try {
    const decoded = await getAuth(firebaseAdmin).verifyIdToken(token);

    let user = await db.query.users.findFirst({
      where: eq(users.firebaseUid, decoded.uid),
    });

    if (!user) {
      [user] = await db
        .insert(users)
        .values({
          firebaseUid: decoded.uid,
          email: decoded.email || "",
          name: decoded.name || null,
          image: decoded.picture || null,
        })
        .returning();
    } else {
      // Sync name and image if they changed
      const nameChanged = decoded.name && user.name !== decoded.name;
      const imageChanged = decoded.picture && user.image !== decoded.picture;
      if (nameChanged || imageChanged) {
        [user] = await db
          .update(users)
          .set({
            name: decoded.name || user.name,
            image: decoded.picture || user.image,
          })
          .where(eq(users.firebaseUid, decoded.uid))
          .returning();
      }
    }

    return {
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        image: user.image,
      },
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("[getSession] verifyIdToken failed:", msg);
    if (process.env.NODE_ENV === "development") {
      console.error("[getSession] full error:", err);
    }
    return null;
  }
}
