import { initializeApp, getApps, cert, applicationDefault } from "firebase-admin/app";
import { readFileSync } from "fs";

function loadServiceAccount(): Record<string, unknown> {
  const inline = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
  if (inline) { console.log("[firebase-admin] Using FIREBASE_SERVICE_ACCOUNT_JSON"); return JSON.parse(inline); }

  const filePath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;
  if (filePath) { console.log("[firebase-admin] Using FIREBASE_SERVICE_ACCOUNT_PATH:", filePath); return JSON.parse(readFileSync(filePath, "utf-8")); }

  const envPath = process.env.GOOGLE_APPLICATION_CREDENTIALS;
  if (envPath) { console.log("[firebase-admin] Using GOOGLE_APPLICATION_CREDENTIALS:", envPath); return JSON.parse(readFileSync(envPath, "utf-8")); }

  const base64 = process.env.FIREBASE_SERVICE_ACCOUNT_BASE64;
  if (base64) { console.log("[firebase-admin] Using FIREBASE_SERVICE_ACCOUNT_BASE64"); return JSON.parse(Buffer.from(base64, "base64").toString("utf-8")); }

  throw new Error(
    "Set FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_SERVICE_ACCOUNT_PATH, " +
    "GOOGLE_APPLICATION_CREDENTIALS, or FIREBASE_SERVICE_ACCOUNT_BASE64"
  );
}

function initApp() {
  if (getApps().length > 0) return getApps()[0];

  try {
    return initializeApp({ credential: cert(loadServiceAccount()) });
  } catch (err) {
    try {
      return initializeApp({ credential: applicationDefault() });
    } catch {
      throw err;
    }
  }
}

export const firebaseAdmin = initApp();
