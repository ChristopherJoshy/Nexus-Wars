# Nexus Wars Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js web app for Nexus Wars: Google OAuth, team management (join-by-code), submission upload (≤5/day), leaderboard, and replay viewer.

**Architecture:** Next.js 15 App Router + Drizzle ORM (PostgreSQL) + Better Auth (Google) + Tailwind CSS + shadcn/ui components. The web app talks to PostgreSQL (team/submission/match data) and MinIO (replay JSON blobs). The worker processes jobs in the background. Docker Desktop is required for local postgres/minio.

**Tech Stack:** Next.js 15, TypeScript, Drizzle ORM, Better Auth, Tailwind CSS, shadcn/ui, PostgreSQL 16, MinIO (S3-compatible)

## Global Constraints

- 1v1 only; ≤500 steps; match <3 min; energy system
- ≤5 submissions per team per day; latest 2 active
- Private validation (only team sees their own); public matches/replays after completion
- Bot actions are angle-based: `[source_planet_id, angle_radians, num_ships]`
- Planet tuple: `[id, owner, x, y, radius, ships, production, energy, energyCap, energyRegen]`
- Replay JSON format: `{ version, engine, engineVersion, seed, configuration, players[], steps[], info }`
- Platform: Windows (Node.js), WSL2 (worker), Docker Desktop (postgres/minio)

---

## Task 1: Scaffold Next.js App

**Files:**
- Create: `services/web/` (full Next.js app)
- Create: `services/web/package.json`
- Create: `services/web/next.config.ts`
- Create: `services/web/tsconfig.json`
- Create: `services/web/tailwind.config.ts`
- Create: `services/web/postcss.config.js`

**Interfaces:**
- Consumes: none (initial scaffold)
- Produces: `services/web/` directory with working Next.js dev server

- [ ] **Step 1: Create Next.js app**

```bash
cd "C:\Users\chris\Documents\Work\Nexus\Nexus Wars"
npx create-next-app@latest services/web --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
```

- [ ] **Step 2: Verify dev server starts**

```bash
cd services/web
npm run dev
# Visit http://localhost:3000 - should show default Next.js page
# Ctrl+C to stop
```

- [ ] **Step 3: Install shadcn/ui**

```bash
cd services/web
npx shadcn@latest init -d
npx shadcn@latest add button card dialog input label table tabs toast
```

- [ ] **Step 4: Install Drizzle ORM**

```bash
cd services/web
npm install drizzle-orm postgres
npm install -D drizzle-kit
```

- [ ] **Step 5: Install Better Auth**

```bash
cd services/web
npm install better-auth
```

- [ ] **Step 6: Commit**

```bash
git add services/web
git commit -m "feat(web): scaffold Next.js app with shadcn, Drizzle, Better Auth"
```

---

## Task 2: Database Schema (Drizzle)

**Files:**
- Create: `services/web/src/lib/db/schema.ts`
- Create: `services/web/src/lib/db/index.ts`
- Create: `services/web/drizzle.config.ts`

**Interfaces:**
- Consumes: Task 1 (Next.js app with Drizzle installed)
- Produces: `db` object with typed tables matching `migrations/0001_init.sql`

- [ ] **Step 1: Write Drizzle schema**

```typescript
// services/web/src/lib/db/schema.ts
import { pgTable, uuid, text, timestamp, doublePrecision, integer, jsonb, pgEnum, index, uniqueIndex } from "drizzle-orm/pg-core";

// Enums
export const submissionStatusEnum = pgEnum("submission_status", [
  "queued", "compiling", "validated", "rejected", "active", "inactive",
]);
export const matchKindEnum = pgEnum("match_kind", ["validation", "rated"]);
export const matchStatusEnum = pgEnum("match_status", [
  "pending", "running", "finished", "errored",
]);
export const matchWinnerEnum = pgEnum("match_winner", ["a", "b", "draw"]);
export const jobTypeEnum = pgEnum("job_type", ["compile", "validate", "run_match"]);
export const jobStatusEnum = pgEnum("job_status", ["pending", "running", "done", "failed"]);

// Users
export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  email: text("email").unique().notNull(),
  name: text("name"),
  googleSub: text("google_sub").unique(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// Teams
export const teams = pgTable("teams", {
  id: uuid("id").primaryKey().defaultRandom(),
  name: text("name").notNull(),
  teamCode: text("team_code").unique().notNull(),
  ownerId: uuid("owner_id").references(() => users.id, { onDelete: "set null" }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// Team Members
export const teamMembers = pgTable("team_members", {
  teamId: uuid("team_id").references(() => teams.id, { onDelete: "cascade" }),
  userId: uuid("user_id").references(() => users.id, { onDelete: "cascade" }),
  role: text("role").notNull().default("member"),
  joinedAt: timestamp("joined_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [uniqueIndex("team_members_pkey").on(t.teamId, t.userId)]);

// Submissions
export const submissions = pgTable("submissions", {
  id: uuid("id").primaryKey().defaultRandom(),
  teamId: uuid("team_id").notNull().references(() => teams.id, { onDelete: "cascade" }),
  userId: uuid("user_id").references(() => users.id, { onDelete: "set null" }),
  status: submissionStatusEnum("status").notNull().default("queued"),
  artifactKey: text("artifact_key"),
  engineVersion: text("engine_version"),
  rejectReason: text("reject_reason"),
  validationReplayKey: text("validation_replay_key"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("idx_subs_team_time").on(t.teamId, t.createdAt)]);

// Ratings
export const ratings = pgTable("ratings", {
  teamId: uuid("team_id").primaryKey().references(() => teams.id, { onDelete: "cascade" }),
  rating: doublePrecision("rating").notNull().default(1500),
  rd: doublePrecision("rd").notNull().default(350),
  volatility: doublePrecision("volatility").notNull().default(0.06),
  lastMatchAt: timestamp("last_match_at", { withTimezone: true }),
  wins: integer("wins").notNull().default(0),
  losses: integer("losses").notNull().default(0),
  draws: integer("draws").notNull().default(0),
  matchesPlayed: integer("matches_played").notNull().default(0),
});

// Matches
export const matches = pgTable("matches", {
  id: uuid("id").primaryKey().defaultRandom(),
  seed: integer("seed"),
  engineVersion: text("engine_version"),
  configurationJson: jsonb("configuration_json").notNull(),
  teamAId: uuid("team_a_id").references(() => teams.id),
  teamBId: uuid("team_b_id").references(() => teams.id),
  submissionAId: uuid("submission_a_id").references(() => submissions.id),
  submissionBId: uuid("submission_b_id").references(() => submissions.id),
  status: matchStatusEnum("status").notNull().default("pending"),
  kind: matchKindEnum("kind").notNull(),
  winner: matchWinnerEnum("winner"),
  reason: text("reason"),
  replayKey: text("replay_key"),
  scores: jsonb("scores"),
  startedAt: timestamp("started_at", { withTimezone: true }),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
  durationMs: integer("duration_ms"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("idx_matches_status").on(t.status),
  index("idx_matches_team").on(t.teamAId, t.teamBId),
]);

// Match Participants
export const matchParticipants = pgTable("match_participants", {
  matchId: uuid("match_id").references(() => matches.id, { onDelete: "cascade" }),
  teamId: uuid("team_id").references(() => teams.id, { onDelete: "cascade" }),
  playerIndex: integer("player_index").notNull(),
  submissionId: uuid("submission_id").references(() => submissions.id),
  ratingBefore: doublePrecision("rating_before"),
  rdBefore: doublePrecision("rd_before"),
  ratingAfter: doublePrecision("rating_after"),
  rdAfter: doublePrecision("rd_after"),
}, (t) => [uniqueIndex("match_participants_pkey").on(t.matchId, t.teamId)]);

// Jobs
export const jobs = pgTable("jobs", {
  id: uuid("id").primaryKey().defaultRandom(),
  type: jobTypeEnum("type").notNull(),
  payloadJson: jsonb("payload_json").notNull().default({}),
  status: jobStatusEnum("status").notNull().default("pending"),
  workerId: text("worker_id"),
  error: text("error"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  startedAt: timestamp("started_at", { withTimezone: true }),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
}, (t) => [index("idx_jobs_pending").on(t.status, t.createdAt)]);

// Replay Objects
export const replayObjects = pgTable("replay_objects", {
  key: text("key").primaryKey(),
  matchId: uuid("match_id").references(() => matches.id, { onDelete: "cascade" }),
  sizeBytes: integer("size_bytes"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
```

- [ ] **Step 2: Create Drizzle client**

```typescript
// services/web/src/lib/db/index.ts
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const connectionString = process.env.DATABASE_URL!;

// For server-side (API routes, server components)
const client = postgres(connectionString);
export const db = drizzle(client, { schema });
```

- [ ] **Step 3: Create Drizzle config**

```typescript
// services/web/drizzle.config.ts
import { defineConfig } from "drizzle-kit";

export default defineConfig({
  schema: "./src/lib/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: {
    url: process.env.DATABASE_URL!,
  },
});
```

- [ ] **Step 4: Run Drizzle generate**

```bash
cd services/web
npx drizzle-kit generate
```

- [ ] **Step 5: Commit**

```bash
git add services/web/src/lib/db services/web/drizzle.config.ts
git commit -m "feat(web): add Drizzle ORM schema matching PostgreSQL migration"
```

---

## Task 3: Better Auth Setup

**Files:**
- Create: `services/web/src/lib/auth.ts`
- Create: `services/web/src/lib/auth-client.ts`
- Create: `services/web/src/app/api/auth/[...all]/route.ts`
- Modify: `services/web/src/app/layout.tsx`

**Interfaces:**
- Consumes: Task 1 (Next.js app), Task 2 (DB schema)
- Produces: `auth` handler, `authClient` for client-side use

- [ ] **Step 1: Create server auth config**

```typescript
// services/web/src/lib/auth.ts
import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { db } from "./db";

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "pg",
  }),
  emailAndPassword: {
    enabled: false,
  },
  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    },
  },
  session: {
    expiresIn: 60 * 60 * 24 * 7, // 7 days
    updateAge: 60 * 60 * 24, // 1 day
  },
});

export type Session = typeof auth.$Infer.Session;
```

- [ ] **Step 2: Create client auth config**

```typescript
// services/web/src/lib/auth-client.ts
import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
});

export const { signIn, signOut, useSession } = authClient;
```

- [ ] **Step 3: Create auth API route**

```typescript
// services/web/src/app/api/auth/[...all]/route.ts
import { auth } from "@/lib/auth";
import { toNextHandler } from "better-auth/next-js";

export const { GET, POST } = toNextHandler(auth);
```

- [ ] **Step 4: Update layout with session provider**

```tsx
// services/web/src/app/layout.tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Nexus Wars",
  description: "1v1 AI Battle Competition",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <nav className="border-b p-4 flex justify-between items-center">
          <a href="/" className="text-xl font-bold">Nexus Wars</a>
          <div className="flex gap-4">
            <a href="/leaderboard" className="hover:underline">Leaderboard</a>
            <a href="/submit" className="hover:underline">Submit</a>
            <a href="/team" className="hover:underline">Team</a>
          </div>
        </nav>
        <main className="container mx-auto p-4">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add services/web/src/lib/auth.ts services/web/src/lib/auth-client.ts \
  services/web/src/app/api/auth services/web/src/app/layout.tsx
git commit -m "feat(web): add Better Auth with Google OAuth"
```

---

## Task 4: API Routes (Teams, Submissions, Leaderboard)

**Files:**
- Create: `services/web/src/app/api/teams/route.ts`
- Create: `services/web/src/app/api/teams/join/route.ts`
- Create: `services/web/src/app/api/submissions/route.ts`
- Create: `services/web/src/app/api/leaderboard/route.ts`
- Create: `services/web/src/app/api/replays/[matchId]/route.ts`

**Interfaces:**
- Consumes: Task 2 (DB schema), Task 3 (auth)
- Produces: API endpoints for all frontend features

- [ ] **Step 1: Create teams API**

```typescript
// services/web/src/app/api/teams/route.ts
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { teams, teamMembers, ratings } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { eq } from "drizzle-orm";

function generateTeamCode(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from({ length: 6 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

export async function POST(req: NextRequest) {
  const session = await auth.api.getSession({ headers: req.headers });
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { name } = await req.json();
  if (!name || name.length < 2) {
    return NextResponse.json({ error: "Team name required" }, { status: 400 });
  }

  // Check if user already has a team
  const existing = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
  });
  if (existing) {
    return NextResponse.json({ error: "Already on a team" }, { status: 409 });
  }

  // Create team + owner membership + initial rating
  const team = await db.transaction(async (tx) => {
    const [t] = await tx.insert(teams).values({
      name,
      teamCode: generateTeamCode(),
      ownerId: session.user.id,
    }).returning();

    await tx.insert(teamMembers).values({
      teamId: t.id,
      userId: session.user.id,
      role: "owner",
    });

    await tx.insert(ratings).values({ teamId: t.id });

    return t;
  });

  return NextResponse.json(team);
}

export async function GET(req: NextRequest) {
  const session = await auth.api.getSession({ headers: req.headers });
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Get user's team
  const membership = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
    with: { team: true },
  });

  if (!membership) {
    return NextResponse.json({ error: "No team" }, { status: 404 });
  }

  return NextResponse.json(membership.team);
}
```

- [ ] **Step 2: Create team join API**

```typescript
// services/web/src/app/api/teams/join/route.ts
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { teams, teamMembers } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { eq } from "drizzle-orm";

export async function POST(req: NextRequest) {
  const session = await auth.api.getSession({ headers: req.headers });
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { teamCode } = await req.json();
  if (!teamCode || teamCode.length !== 6) {
    return NextResponse.json({ error: "Invalid team code" }, { status: 400 });
  }

  // Check if user already on a team
  const existing = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
  });
  if (existing) {
    return NextResponse.json({ error: "Already on a team" }, { status: 409 });
  }

  // Find team by code
  const team = await db.query.teams.findFirst({
    where: eq(teams.teamCode, teamCode.toUpperCase()),
  });
  if (!team) {
    return NextResponse.json({ error: "Team not found" }, { status: 404 });
  }

  // Join team
  await db.insert(teamMembers).values({
    teamId: team.id,
    userId: session.user.id,
    role: "member",
  });

  return NextResponse.json(team);
}
```

- [ ] **Step 3: Create submissions API**

```typescript
// services/web/src/app/api/submissions/route.ts
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { submissions, teamMembers } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { eq, and, gte, sql } from "drizzle-orm";

const MAX_SUBMISSIONS_PER_DAY = 5;

export async function POST(req: NextRequest) {
  const session = await auth.api.getSession({ headers: req.headers });
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Get user's team
  const membership = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
  });
  if (!membership) {
    return NextResponse.json({ error: "No team" }, { status: 400 });
  }

  // Check daily limit
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const [countResult] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(submissions)
    .where(
      and(
        eq(submissions.teamId, membership.teamId),
        gte(submissions.createdAt, today)
      )
    );
  if ((countResult?.count ?? 0) >= MAX_SUBMISSIONS_PER_DAY) {
    return NextResponse.json(
      { error: `Daily limit of ${MAX_SUBMISSIONS_PER_DAY} submissions reached` },
      { status: 429 }
    );
  }

  // Handle file upload
  const formData = await req.formData();
  const file = formData.get("file") as File | null;
  if (!file) {
    return NextResponse.json({ error: "No file" }, { status: 400 });
  }

  // Validate file type
  const validTypes = [".zip", ".tar.gz", ".tgz", ".py"];
  const ext = file.name.split(".").pop();
  if (!validTypes.includes(`.${ext}`)) {
    return NextResponse.json(
      { error: "Invalid file type. Upload .zip, .tar.gz, or .py" },
      { status: 400 }
    );
  }

  // TODO: Upload to MinIO/S3, create submission record, enqueue validation job
  // For now, create the record with artifact_key = filename
  const [sub] = await db.insert(submissions).values({
    teamId: membership.teamId,
    userId: session.user.id,
    status: "queued",
    artifactKey: file.name,
    engineVersion: "2026.1.0",
  }).returning();

  // TODO: Enqueue validation job
  // await db.insert(jobs).values({ type: "validate", payloadJson: { submissionId: sub.id } });

  return NextResponse.json(sub);
}

export async function GET(req: NextRequest) {
  const session = await auth.api.getSession({ headers: req.headers });
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const membership = await db.query.teamMembers.findFirst({
    where: eq(teamMembers.userId, session.user.id),
  });
  if (!membership) {
    return NextResponse.json([]);
  }

  const subs = await db.query.submissions.findMany({
    where: eq(submissions.teamId, membership.teamId),
    orderBy: (subs, { desc }) => [desc(subs.createdAt)],
    limit: 20,
  });

  return NextResponse.json(subs);
}
```

- [ ] **Step 4: Create leaderboard API**

```typescript
// services/web/src/app/api/leaderboard/route.ts
import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { ratings, teams } from "@/lib/db/schema";
import { desc } from "drizzle-orm";

export async function GET() {
  const board = await db
    .select({
      teamId: ratings.teamId,
      teamName: teams.name,
      rating: ratings.rating,
      rd: ratings.rd,
      wins: ratings.wins,
      losses: ratings.losses,
      draws: ratings.draws,
      matchesPlayed: ratings.matchesPlayed,
    })
    .from(ratings)
    .innerJoin(teams, eq(ratings.teamId, teams.id))
    .orderBy(desc(ratings.rating))
    .limit(100);

  return NextResponse.json(board);
}
```

- [ ] **Step 5: Create replay API**

```typescript
// services/web/src/app/api/replays/[matchId]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { matches, replayObjects } from "@/lib/db/schema";
import { eq } from "drizzle-orm";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ matchId: string }> }
) {
  const { matchId } = await params;

  const match = await db.query.matches.findFirst({
    where: eq(matches.id, matchId),
  });
  if (!match) {
    return NextResponse.json({ error: "Match not found" }, { status: 404 });
  }

  if (!match.replayKey) {
    return NextResponse.json({ error: "Replay not available" }, { status: 404 });
  }

  // TODO: Fetch replay JSON from MinIO/S3 using match.replayKey
  // For now, return the match metadata
  return NextResponse.json({
    match,
    replayUrl: `/api/replays/${matchId}/blob`,
  });
}
```

- [ ] **Step 6: Commit**

```bash
git add services/web/src/app/api
git commit -m "feat(web): add API routes for teams, submissions, leaderboard, replays"
```

---

## Task 5: Frontend Pages

**Files:**
- Create: `services/web/src/app/page.tsx` (home)
- Create: `services/web/src/app/leaderboard/page.tsx`
- Create: `services/web/src/app/team/page.tsx`
- Create: `services/web/src/app/submit/page.tsx`
- Create: `services/web/src/app/replay/[matchId]/page.tsx`

**Interfaces:**
- Consumes: Task 3 (auth), Task 4 (API routes)
- Produces: All user-facing pages

- [ ] **Step 1: Home page**

```tsx
// services/web/src/app/page.tsx
export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh]">
      <h1 className="text-6xl font-bold mb-4">Nexus Wars</h1>
      <p className="text-xl text-muted-foreground mb-8">
        1v1 AI Battle Competition
      </p>
      <div className="flex gap-4">
        <a href="/submit" className="bg-primary text-primary-foreground px-6 py-3 rounded-lg font-medium hover:opacity-90">
          Submit Bot
        </a>
        <a href="/leaderboard" className="border px-6 py-3 rounded-lg font-medium hover:bg-muted">
          Leaderboard
        </a>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Leaderboard page**

```tsx
// services/web/src/app/leaderboard/page.tsx
"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface LeaderboardEntry {
  teamId: string;
  teamName: string;
  rating: number;
  rd: number;
  wins: number;
  losses: number;
  draws: number;
  matchesPlayed: number;
}

export default function LeaderboardPage() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/leaderboard")
      .then((res) => res.json())
      .then((data) => {
        setEntries(data);
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Leaderboard</h1>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Team</TableHead>
                <TableHead>Rating</TableHead>
                <TableHead>W</TableHead>
                <TableHead>L</TableHead>
                <TableHead>D</TableHead>
                <TableHead>Matches</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e, i) => (
                <TableRow key={e.teamId}>
                  <TableCell>{i + 1}</TableCell>
                  <TableCell className="font-medium">{e.teamName}</TableCell>
                  <TableCell>{Math.round(e.rating)}</TableCell>
                  <TableCell>{e.wins}</TableCell>
                  <TableCell>{e.losses}</TableCell>
                  <TableCell>{e.draws}</TableCell>
                  <TableCell>{e.matchesPlayed}</TableCell>
                </TableRow>
              ))}
              {entries.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    {loading ? "Loading..." : "No teams yet"}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Team page**

```tsx
// services/web/src/app/team/page.tsx
"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

export default function TeamPage() {
  const [team, setTeam] = useState<any>(null);
  const [teamName, setTeamName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/teams")
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error("No team");
      })
      .then(setTeam)
      .catch(() => setTeam(null))
      .finally(() => setLoading(false));
  }, []);

  const createTeam = async () => {
    const res = await fetch("/api/teams", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: teamName }),
    });
    if (res.ok) setTeam(await res.json());
  };

  const joinTeam = async () => {
    const res = await fetch("/api/teams/join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teamCode: joinCode }),
    });
    if (res.ok) setTeam(await res.json());
  };

  if (loading) return <div>Loading...</div>;

  if (team) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">{team.name}</h1>
        <Card>
          <CardHeader>
            <CardTitle>Team Code</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-mono tracking-widest">{team.team_code}</p>
            <p className="text-sm text-muted-foreground mt-2">
              Share this code with teammates
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-md">
      <h1 className="text-3xl font-bold">Join the Competition</h1>
      <Card>
        <CardHeader>
          <CardTitle>Create Team</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Team Name</Label>
            <Input value={teamName} onChange={(e) => setTeamName(e.target.value)} />
          </div>
          <Button onClick={createTeam} disabled={!teamName}>Create</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Join Team</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Team Code</Label>
            <Input value={joinCode} onChange={(e) => setJoinCode(e.target.value)} maxLength={6} />
          </div>
          <Button onClick={joinTeam} disabled={joinCode.length !== 6}>Join</Button>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Submit page**

```tsx
// services/web/src/app/submit/page.tsx
"use client";

import { useEffect, useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface Submission {
  id: string;
  status: string;
  artifact_key: string;
  created_at: string;
}

export default function SubmitPage() {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/submissions")
      .then((res) => res.json())
      .then(setSubmissions);
  }, []);

  const upload = async () => {
    if (!fileRef.current?.files?.[0]) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", fileRef.current.files[0]);
    const res = await fetch("/api/submissions", { method: "POST", body: formData });
    if (res.ok) {
      const sub = await res.json();
      setSubmissions((prev) => [sub, ...prev]);
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Submit Bot</h1>
      <Card>
        <CardHeader>
          <CardTitle>Upload</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-4">
          <input ref={fileRef} type="file" accept=".zip,.tar.gz,.tgz,.py" className="flex-1" />
          <Button onClick={upload} disabled={uploading}>
            {uploading ? "Uploading..." : "Submit"}
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recent Submissions</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>File</TableHead>
                <TableHead>Submitted</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {submissions.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <span className={`px-2 py-1 rounded text-xs ${
                      s.status === "active" ? "bg-green-100 text-green-800" :
                      s.status === "validated" ? "bg-blue-100 text-blue-800" :
                      s.status === "rejected" ? "bg-red-100 text-red-800" :
                      "bg-gray-100 text-gray-800"
                    }`}>
                      {s.status}
                    </span>
                  </TableCell>
                  <TableCell>{s.artifact_key}</TableCell>
                  <TableCell>{new Date(s.created_at).toLocaleDateString()}</TableCell>
                </TableRow>
              ))}
              {submissions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-muted-foreground">
                    No submissions yet
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Replay viewer page**

```tsx
// services/web/src/app/replay/[matchId]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ReplayData {
  version: string;
  engine: string;
  seed: number;
  configuration: any;
  players: { playerId: number }[];
  steps: any[];
  info: {
    winner: number | null;
    reason: string;
    scores: number[];
    durationMs: number;
    steps: number;
  };
}

export default function ReplayPage({ params }: { params: Promise<{ matchId: string }> }) {
  const [matchId, setMatchId] = useState<string>("");
  const [replay, setReplay] = useState<ReplayData | null>(null);
  const [step, setStep] = useState(0);

  useEffect(() => {
    params.then((p) => {
      setMatchId(p.matchId);
      fetch(`/api/replays/${p.matchId}`)
        .then((res) => res.json())
        .then((data) => {
          // TODO: fetch actual replay blob from S3
          // For now, show match metadata
          setReplay(null);
        });
    });
  }, [params]);

  if (!replay) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Replay</h1>
        <Card>
          <CardContent className="p-6">
            <p className="text-muted-foreground">
              Replay viewer coming soon. Match ID: {matchId}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Replay</h1>
      <Card>
        <CardHeader>
          <CardTitle>
            Match #{matchId.slice(0, 8)} — Seed {replay.seed}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4 text-sm">
            <span>Steps: {replay.info.steps}</span>
            <span>Duration: {(replay.info.durationMs / 1000).toFixed(1)}s</span>
            <span>Winner: {replay.info.winner !== null ? `Player ${replay.info.winner}` : "Draw"}</span>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>
              Prev
            </Button>
            <span className="px-4 py-2">{step} / {replay.steps.length - 1}</span>
            <Button variant="outline" onClick={() => setStep(Math.min(replay.steps.length - 1, step + 1))} disabled={step === replay.steps.length - 1}>
              Next
            </Button>
          </div>
          {/* TODO: Canvas-based replay visualization */}
          <div className="h-96 bg-muted rounded-lg flex items-center justify-center">
            <span className="text-muted-foreground">Replay visualization (TODO)</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add services/web/src/app/page.tsx services/web/src/app/leaderboard \
  services/web/src/app/team services/web/src/app/submit \
  services/web/src/app/replay
git commit -m "feat(web): add home, leaderboard, team, submit, replay pages"
```

---

## Task 6: Fix Imports + Verify Build

**Files:**
- Modify: `services/web/src/app/api/leaderboard/route.ts` (fix missing `eq` import)
- Modify: `services/web/src/app/replay/[matchId]/page.tsx` (fix missing Button import)

**Interfaces:**
- Consumes: Tasks 1-5
- Produces: Clean build with no TypeScript errors

- [ ] **Step 1: Fix leaderboard import**

```typescript
// services/web/src/app/api/leaderboard/route.ts
import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { ratings, teams } from "@/lib/db/schema";
import { eq, desc } from "drizzle-orm";
```

- [ ] **Step 2: Fix replay page import**

```tsx
// services/web/src/app/replay/[matchId]/page.tsx
import { Button } from "@/components/ui/button";
```

- [ ] **Step 3: Run build**

```bash
cd services/web
npm run build
```

- [ ] **Step 4: Commit**

```bash
git add services/web
git commit -m "fix(web): fix TypeScript imports and build errors"
```

---

## Task 7: .env.local Template

**Files:**
- Create: `services/web/.env.example`

**Interfaces:**
- Consumes: Tasks 1-6
- Produces: Environment variable template

- [ ] **Step 1: Create .env.example**

```bash
# Database
DATABASE_URL=postgresql://nexus:nexus@localhost:5432/nexus

# Better Auth
BETTER_AUTH_SECRET=your-secret-here
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
NEXT_PUBLIC_APP_URL=http://localhost:3000

# S3/MinIO (for replays)
S3_ENDPOINT=http://localhost:9000
S3_REGION=us-east-1
S3_BUCKET=nexus-replays
S3_ACCESS_KEY=nexus
S3_SECRET_KEY=nexusnexus
```

- [ ] **Step 2: Commit**

```bash
git add services/web/.env.example
git commit -m "feat(web): add environment variable template"
```

---

## Task 8: Fix Docker Compose Build Context

**Files:**
- Modify: `deploy/docker-compose.yml`

**Interfaces:**
- Consumes: Task 1-7 (all web app files)
- Produces: Correct build context for worker Docker image

- [ ] **Step 1: Fix build context**

```yaml
# deploy/docker-compose.yml
  worker:
    build:
      context: .                          # project root (not services/worker)
      dockerfile: deploy/Dockerfile.worker
```

- [ ] **Step 2: Commit**

```bash
git add deploy/docker-compose.yml
git commit -m "fix(deploy): correct Docker build context to project root"
```

---

## Task 9: Integration Test (Docker Required)

**Files:**
- Create: `tests/test_web_integration.py`

**Interfaces:**
- Consumes: Tasks 1-8
- Produces: End-to-end test (requires Docker Desktop)

**Prerequisite:** Docker Desktop must be installed and running.

- [ ] **Step 1: Write integration test**

```python
"""Integration test: full stack (postgres + minio + worker + web)."""
import subprocess
import time
import requests

COMPOSE = "deploy/docker-compose.yml"
WEB = "http://localhost:3000"
API = "http://localhost:3000/api"

def test_postgres():
    import psycopg
    conn = psycopg.connect("postgresql://nexus:nexus@localhost:5432/nexus")
    cur = conn.execute("SELECT 1")
    assert cur.fetchone()[0] == 1
    conn.close()

def test_minio():
    import requests
    r = requests.get("http://localhost:9000/minio/health/live")
    assert r.status_code == 200

def test_leaderboard_empty():
    r = requests.get(f"{API}/leaderboard")
    assert r.status_code == 200
    assert r.json() == []

def test_homepage():
    r = requests.get(WEB)
    assert r.status_code == 200
    assert "Nexus Wars" in r.text
```

- [ ] **Step 2: Run integration test**

```bash
# Start stack
docker compose -f deploy/docker-compose.yml up -d postgres minio mc

# Wait for services
sleep 10

# Run tests
python -m pytest tests/test_web_integration.py -v

# Stop stack
docker compose -f deploy/docker-compose.yml down
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_integration.py
git commit -m "test: add integration tests for full stack"
```
