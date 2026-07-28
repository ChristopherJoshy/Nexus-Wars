# Nexus Wars — Codebase Audit

## Routes & Pages

| Route | Page | Backend? | Status |
|---|---|---|---|
| `/` | Overview (docs + sidebar) | None needed | REAL content, MOCK sidebar |
| `/leaderboard` | Leaderboard table | `GET /api/leaderboard` | REAL (live from DB) |
| `/team` | Team mgmt + invites | `GET/POST /api/teams`, `POST /api/teams/join` | REAL |
| `/submit` | Submissions + upload | `GET/POST /api/submissions` | REAL (but cap is wrong) |
| `/replay` | Match list + viewer | `GET /api/replays` + `GET /api/replays/[id]` | REAL (falls back to mock) |
| `/replay/[matchId]` | Single match viewer | same | REAL (falls back to mock) |

## Mock / Fake / Broken Elements

| # | Element | Location | Status | Fix |
|---|---|---|---|---|
| 1 | Search bar (global) | `TopBar.tsx:19` | MOCK — decorative input, no handler | Remove or wire |
| 2 | Notification bell | `TopBar.tsx:33` | MOCK — decorative button | Remove or wire |
| 3 | "Play in Browser" button | `CompetitionHeader.tsx:130` | BROKEN — links to /submit | Wire to replay viewer |
| 4 | "Live 2D" badge + canvas | `CompetitionHeader.tsx:9-98` | MOCK — decorative animation, not a real match | Replace with static diagram or live match |
| 5 | Files sidebar (3 files, 16.81 kB, Type, License, Data Explorer, Download All) | `page.tsx:342-394` | ALL MOCK — hardcoded values, no real downloads | Replace with Resources section |
| 6 | Raw Data button | `leaderboard/page.tsx:119` | MOCK — no export handler | Wire CSV/JSON download |
| 7 | "2 or 4 players" in metadata + subtitle | `layout.tsx:11`, `CompetitionHeader.tsx:121` | BROKEN — contradicts 1v1-only rule | Fix both |
| 8 | Submissions — no 5-bot cap | `api/submissions/route.ts:9` | WRONG — has 5/day cap, not 5 total | Change to 5 total |
| 9 | Submissions — no cap messaging in UI | `submit/page.tsx` | MISSING | Add cap info + remaining count |
| 10 | Replay mock fallback | `replay/page.tsx:116-132`, `replay/[matchId]/page.tsx:116-131` | BROKEN — uses `generateMockReplay()` on fetch failure | Remove mock fallback |
| 11 | Competition state (open/closed) | not present | MISSING — no backend field, no banner | Add table + field |
| 12 | Leaderboard "Refresh" | `leaderboard/page.tsx:124` | REAL — works | OK |
| 13 | 4-player game preview dots | `CompetitionHeader.tsx:24-28` | BROKEN — 3 planets shown, implies >2 players | Keep but only 2 colored dots |
| 14 | Sidebar unlabeled icons | `Sidebar.tsx:82-96` (More/Settings) | MOCK — decorative, no function | Remove or label |

## DB Schema (Drizzle `schema.ts`)

| Table | Key columns | Status |
|---|---|---|
| `users` | id, firebase_uid, email, name, image | OK |
| `teams` | id, name, team_code (6-char), owner_id | OK |
| `team_members` | team_id, user_id, role | OK |
| `submissions` | id, team_id, user_id, status (enum: queued/compiling/validated/rejected/active/inactive), artifact_key, reject_reason, validation_replay_key | OK — but status enum doesn't include "errored" |
| `ratings` | team_id (PK), rating, rd, volatility, last_match_at, wins, losses, draws, matches_played | OK — Glicko-2 fields |
| `matches` | id, seed, team_a/b_id, submission_a/b_id, status/kind/winner (enums), replay_key, scores, configuration_json | OK — 1v1 only |
| `match_participants` | match_id, team_id, player_index, submission_id, rating_before/after, rd_before/after | OK |
| `jobs` | id, type (compile/validate/run_match), payload_json, status | OK |
| `replay_objects` | key (PK), match_id, size_bytes | OK |

## Schema Changes Needed

- `competitions` table — id, slug, title, status (open/closed/completed), created_at
- `submissions` — add unique constraint (team_id, idx for ordering), change cap enforcement to 5 total (done in app code)
- Remove unused `compile` job type

## Backend Systems Status

| System | Status | Notes |
|---|---|---|
| Matchmaking | REAL | `matchmaker.py` — pairs active submissions by rating proximity, 1v1 only. Runs every ~30s from worker loop. |
| Rating | REAL | Glicko-2 in `rating/glicko2.py` — rate_match(), with RD decay over time. Persisted to `ratings` + `match_participants`. |
| Submission cap (latest 2) | REAL | `promote_submissions()` in `jobs.py` marks latest 2 validated as `active`, rest as `inactive`. Correct. |
| Sandbox | REAL | nsjail support with `USE_NSJAIL=1`, seccomp filtering, CPU/time/mem limits. Falls back to raw subprocess. |
| Replay storage | REAL | MinIO/S3 keyed by `rated/{matchId}.json`, `validation/{subId}.json`. Also local fallback. |
| Team invites | REAL | 6-char `team_code` in `teams` table, validated on join. |
| Competition state | MISSING | No concept of open/closed/completed anywhere. |
| 5-submission total cap | BROKEN | Currently 5/day. Need 5 total. |

## Visual Design Assessment

**Current state**: Generic dark-mode SaaS template. `#111214` background, `#38bdf8` accent blue, rounded pill buttons everywhere, centered cards, flat sidebar of unlabeled icons. Default Inter/Geist fonts. No visual language for ships vs energy.

**Goal**: Control-room / star-chart aesthetic. Monospace for data, humanist sans for headings. Distinct cool-blue (ships) / warm-gold (energy) color language. Asymmetric layouts. Radial/orbit motif in backgrounds.
