import {
  pgTable,
  uuid,
  text,
  timestamp,
  doublePrecision,
  integer,
  jsonb,
  pgEnum,
  index,
  uniqueIndex,
} from "drizzle-orm/pg-core";

export const competitionStatusEnum = pgEnum("competition_status", [
  "open",
  "closed",
  "completed",
]);

export const submissionStatusEnum = pgEnum("submission_status", [
  "queued",
  "validated",
  "rejected",
  "active",
  "inactive",
  "errored",
]);
export const matchKindEnum = pgEnum("match_kind", ["validation", "rated"]);
export const matchStatusEnum = pgEnum("match_status", [
  "pending",
  "running",
  "finished",
  "errored",
]);
export const matchWinnerEnum = pgEnum("match_winner", ["a", "b", "draw"]);
export const jobTypeEnum = pgEnum("job_type", [
  "validate",
  "run_match",
]);
export const jobStatusEnum = pgEnum("job_status", [
  "pending",
  "running",
  "done",
  "failed",
]);

export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  firebaseUid: text("firebase_uid").unique().notNull(),
  email: text("email").notNull(),
  name: text("name"),
  image: text("image"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const competitions = pgTable("competitions", {
  id: uuid("id").primaryKey().defaultRandom(),
  slug: text("slug").unique().notNull(),
  title: text("title").notNull(),
  status: competitionStatusEnum("status").notNull().default("open"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const teams = pgTable("teams", {
  id: uuid("id").primaryKey().defaultRandom(),
  name: text("name").notNull(),
  teamCode: text("team_code").unique().notNull(),
  ownerId: uuid("owner_id").references(() => users.id, {
    onDelete: "set null",
  }),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const teamMembers = pgTable(
  "team_members",
  {
    teamId: uuid("team_id")
      .references(() => teams.id, { onDelete: "cascade" })
      .notNull(),
    userId: uuid("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    role: text("role").notNull().default("member"),
    joinedAt: timestamp("joined_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (t) => [uniqueIndex("team_members_pkey").on(t.teamId, t.userId)]
);

export const submissions = pgTable(
  "submissions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    teamId: uuid("team_id")
      .notNull()
      .references(() => teams.id, { onDelete: "cascade" }),
    userId: uuid("user_id").references(() => users.id, {
      onDelete: "set null",
    }),
    status: submissionStatusEnum("status").notNull().default("queued"),
    artifactKey: text("artifact_key"),
    engineVersion: text("engine_version"),
    rejectReason: text("reject_reason"),
    validationReplayKey: text("validation_replay_key"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (t) => [index("idx_subs_team_time").on(t.teamId, t.createdAt)]
);

export const ratings = pgTable("ratings", {
  teamId: uuid("team_id")
    .primaryKey()
    .references(() => teams.id, { onDelete: "cascade" }),
  rating: doublePrecision("rating").notNull().default(600),
  rd: doublePrecision("rd").notNull().default(350),
  volatility: doublePrecision("volatility").notNull().default(0.06),
  lastMatchAt: timestamp("last_match_at", { withTimezone: true }),
  wins: integer("wins").notNull().default(0),
  losses: integer("losses").notNull().default(0),
  draws: integer("draws").notNull().default(0),
  matchesPlayed: integer("matches_played").notNull().default(0),
});

export const matches = pgTable(
  "matches",
  {
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
    competitionId: uuid("competition_id").references(() => competitions.id),
    startedAt: timestamp("started_at", { withTimezone: true }),
    finishedAt: timestamp("finished_at", { withTimezone: true }),
    durationMs: integer("duration_ms"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (t) => [
    index("idx_matches_status").on(t.status),
    index("idx_matches_team").on(t.teamAId, t.teamBId),
  ]
);

export const matchParticipants = pgTable(
  "match_participants",
  {
    matchId: uuid("match_id")
      .references(() => matches.id, { onDelete: "cascade" })
      .notNull(),
    teamId: uuid("team_id")
      .references(() => teams.id, { onDelete: "cascade" })
      .notNull(),
    playerIndex: integer("player_index").notNull(),
    submissionId: uuid("submission_id").references(() => submissions.id),
    ratingBefore: doublePrecision("rating_before"),
    rdBefore: doublePrecision("rd_before"),
    ratingAfter: doublePrecision("rating_after"),
    rdAfter: doublePrecision("rd_after"),
  },
  (t) => [uniqueIndex("match_participants_pkey").on(t.matchId, t.teamId)]
);

export const jobs = pgTable(
  "jobs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    type: jobTypeEnum("type").notNull(),
    payloadJson: jsonb("payload_json").notNull().default({}),
    status: jobStatusEnum("status").notNull().default("pending"),
    workerId: text("worker_id"),
    error: text("error"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    startedAt: timestamp("started_at", { withTimezone: true }),
    finishedAt: timestamp("finished_at", { withTimezone: true }),
  },
  (t) => [index("idx_jobs_pending").on(t.status, t.createdAt)]
);

export const replayObjects = pgTable("replay_objects", {
  key: text("key").primaryKey(),
  matchId: uuid("match_id").references(() => matches.id, {
    onDelete: "cascade",
  }),
  sizeBytes: integer("size_bytes"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});


export const settings = pgTable("settings", {
  key: text("key").primaryKey(),
  value: jsonb("value").notNull().default("true"),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});


// Better Auth relations (removed — migrated to Firebase Auth)
