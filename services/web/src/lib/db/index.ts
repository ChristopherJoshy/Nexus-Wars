import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error(
    "DATABASE_URL environment variable is not set. " +
    "Set it to a PostgreSQL connection string, e.g.: " +
    "postgresql://nexus:nexus@16.170.239.106:5432/nexus"
  );
}

const client = postgres(connectionString, {
  connect_timeout: 10,
});
export const db = drizzle(client, { schema });
