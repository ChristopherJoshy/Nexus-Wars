"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { Upload, Zap, Clock, Play, Loader2, RefreshCw } from "lucide-react";
import { useSession, signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { animate } from "animejs";

function useResetCountdown() {
  const [timeLeft, setTimeLeft] = useState("");

  useEffect(() => {
    const calculate = () => {
      const now = new Date();
      const nextReset = new Date(
        Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1, 0, 0, 0)
      );
      const diffMs = nextReset.getTime() - now.getTime();
      if (diffMs <= 0) {
        setTimeLeft("resets now");
        return;
      }
      const hours = Math.floor(diffMs / (1000 * 60 * 60));
      const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);
      setTimeLeft(`${hours}h ${minutes}m ${seconds}s`);
    };

    calculate();
    const interval = setInterval(calculate, 1000);
    return () => clearInterval(interval);
  }, []);

  return timeLeft;
}

interface Submission {
  id: string;
  status: string;
  artifactKey?: string;
  artifact_key?: string;
  createdAt?: string;
  created_at?: string;
  score?: number;
  rating?: number | null;
  rd?: number | null;
  wins?: number;
  losses?: number;
  draws?: number;
  matchesPlayed?: number;
}

interface SubmissionsResponse {
  submissions: Submission[];
  totalCount: number;
  maxSubmissions: number;
  submissionsPaused?: boolean;
}

function formatRelativeTime(dateInput: Date | string | number | null | undefined): string {
  if (!dateInput) return "Just now";
  const date = typeof dateInput === "string" || typeof dateInput === "number" ? new Date(dateInput) : dateInput;
  if (isNaN(date.getTime())) return "Just now";
  const now = new Date();
  const diffMs = Math.max(0, now.getTime() - date.getTime());
  const diffSecs = Math.floor(diffMs / 1000);
  if (diffSecs < 60) return "Just now";
  const diffMins = Math.floor(diffSecs / 60);
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths}mo ago`;
  const diffYears = Math.floor(diffDays / 365);
  return `${diffYears}y ago`;
}

export default function SubmissionsPage() {
  const { data: session, isPending } = useSession();
  const resetCountdown = useResetCountdown();
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [maxSubmissions, setMaxSubmissions] = useState(5);
  const [submissionsPaused, setSubmissionsPaused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [autoRefreshing, setAutoRefreshing] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [filter, setFilter] = useState<"all" | "successful" | "errors">("all");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasTeam, setHasTeam] = useState<boolean | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const tableRef = useRef<HTMLTableSectionElement>(null);

  // Initial fetch and manual reload handler
  useEffect(() => {
    if (!session) return;

    let isCurrent = true;
    const headers: Record<string, string> = { Authorization: `Bearer ${session.token}` };

    fetch("/api/teams", { headers })
      .then((res) => {
        if (res.ok) {
          setHasTeam(true);
          return fetch("/api/submissions", { headers });
        } else if (res.status === 404) {
          setHasTeam(false);
          return null;
        } else {
          throw new Error("Failed team verification");
        }
      })
      .then((res) => {
        if (!res) return;
        if (!res.ok) throw new Error("Load failed");
        return res.json();
      })
      .then((data: SubmissionsResponse) => {
        if (isCurrent && data) {
          setSubmissions(data.submissions || []);
          setTotalCount(data.totalCount ?? 0);
          setMaxSubmissions(data.maxSubmissions ?? 5);
          setSubmissionsPaused(Boolean(data.submissionsPaused));
          setLoading(false);
          setAutoRefreshing(false);
        }
      })
      .catch(() => {
        if (isCurrent) {
          setSubmissions([]);
          setLoading(false);
          setAutoRefreshing(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [session, reloadToken]);

  // Quiet 30-second background auto-refresh & visibility recovery
  useEffect(() => {
    if (!session || hasTeam === false) return;

    const fetchQuietly = () => {
      if (document.visibilityState !== "visible") return;
      setAutoRefreshing(true);
      const headers = { Authorization: `Bearer ${session.token}` };

      fetch("/api/submissions", { headers })
        .then((res) => (res.ok ? res.json() : null))
        .then((data: SubmissionsResponse | null) => {
          if (data) {
            setSubmissions(data.submissions || []);
            setTotalCount(data.totalCount ?? 0);
            setMaxSubmissions(data.maxSubmissions ?? 5);
          }
        })
        .finally(() => setAutoRefreshing(false));
    };

    const interval = setInterval(fetchQuietly, 30000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        fetchQuietly();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [session, hasTeam]);

  const refreshSubmissions = () => {
    setLoading(true);
    setReloadToken((t) => t + 1);
  };

  useEffect(() => {
    if (!loading && submissions.length > 0 && tableRef.current) {
      animate(tableRef.current.querySelectorAll(".sub-row-anim"), {
        opacity: [0, 1],
        translateX: [-8, 0],
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delay: (_el: any, i = 0) => i * 35,
        duration: 400,
        ease: "outQuint",
      });
    }
  }, [loading, submissions]);

  if (isPending) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-3 font-mono">
        <div className="w-7 h-7 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <span className="text-xs text-muted-foreground uppercase tracking-widest animate-pulse">
          Loading Session...
        </span>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-5 text-center max-w-md mx-auto">
        <h2 className="text-xl font-bold text-foreground uppercase">[ ACCESS_DENIED ]</h2>
        <p className="text-muted-foreground text-xs leading-relaxed">
          Authentication is required to upload bots. Please sign in with your Google account.
        </p>
        <Button
          onClick={() => signIn.social({ provider: "google" })}
          className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-6 py-2"
        >
          Sign In with Google
        </Button>
      </div>
    );
  }

  if (hasTeam === false) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-4 text-center max-w-md mx-auto">
        <h2 className="text-lg font-bold text-foreground uppercase">[ NO_TEAM_FOUND ]</h2>
        <p className="text-muted-foreground text-xs leading-relaxed">
          You must be part of a team to submit bot packages. Please create or join a team.
        </p>
        <Link
          href="/team"
          className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-6 py-2 block text-center"
        >
          Go to Team Console
        </Link>
      </div>
    );
  }

  const upload = async () => {
    if (!fileRef.current?.files?.[0] || !session) return;
    setUploading(true);
    setError(null);
    const formData = new FormData();
    formData.append("file", fileRef.current.files[0]);

    try {
      const res = await fetch("/api/submissions", {
        method: "POST",
        headers: { Authorization: `Bearer ${session.token}` },
        body: formData,
      });
      if (res.ok) {
        const sub = await res.json();
        setSubmissions((prev) => [sub, ...prev]);
        setTotalCount((c) => c + 1);
      } else {
        const err = await res.json().catch(() => ({ error: "Upload failed" }));
        setError(err.error || "Upload failed");
      }
    } catch {
      setError("Network error during upload");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const filteredSubmissions = submissions.filter((s) => {
    const isErr = s.status === "error" || s.status === "failed" || s.status === "rejected" || s.status === "errored";
    if (filter === "successful") return !isErr;
    if (filter === "errors") return isErr;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Cap Info + Upload */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <div>
            <h2 className="text-xl font-bold text-foreground tracking-tight">Submissions</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Upload Python bots to compete on the live ladder.
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground font-mono">
            <span className="font-semibold text-foreground">{totalCount}/{maxSubmissions} used</span>
            <span className="text-border">&bull;</span>
            <span className="flex items-center gap-1 text-[10px]">
              <Clock className="w-3 h-3 text-amber-700 shrink-0" />
              <span>Reset in <strong className="text-foreground">{resetCountdown || "..."}</strong></span>
            </span>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              loading={loading || autoRefreshing}
              onClick={refreshSubmissions}
              className="nexus-pill bg-muted border-border text-foreground hover:bg-accent text-xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading || autoRefreshing ? "animate-spin" : ""}`} />
              Refresh
            </Button>

            <input
              ref={fileRef}
              type="file"
              accept=".py"
              className="hidden"
              id="bot-upload-file"
              onChange={upload}
              disabled={uploading}
            />
            <label
              htmlFor="bot-upload-file"
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground font-sans font-semibold text-xs shadow-xs transition-all cursor-pointer active:scale-95 ${
                totalCount >= maxSubmissions || uploading || submissionsPaused ? "opacity-60 pointer-events-none" : ""
              }`}
            >
              {uploading ? (
                <Loader2 className="w-4 h-4 animate-spin shrink-0" />
              ) : (
                <Upload className="w-4 h-4 shrink-0" />
              )}
              <span>{uploading ? "Uploading Bot..." : "Upload Bot (.py)"}</span>
            </label>
          </div>
        </div>
      </div>

      {submissionsPaused && (
        <div className="bg-amber-500/10 border border-amber-500/30 text-amber-600 dark:text-amber-400 rounded-lg p-3 text-xs flex items-center gap-2 font-mono">
          <Zap className="w-4 h-4 shrink-0 text-amber-500" />
          <span>[ PAUSED ] All new bot submissions are currently paused by the administrator.</span>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-destructive rounded-lg p-3 text-xs flex justify-between items-start gap-4">
          <div className="flex items-start gap-2">
            <Zap className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="underline cursor-pointer shrink-0">
            Dismiss
          </button>
        </div>
      )}

      {/* Cap info bar */}
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground bg-muted border border-border rounded-lg px-4 py-2">
        <Zap className="w-3.5 h-3.5 text-amber-700 shrink-0" />
        <span>
          Maximum <strong className="text-foreground">{maxSubmissions} submissions</strong> per team per day.
          Only the latest <strong className="text-foreground">2 active</strong> submissions compete in matchmaking.
          Older submissions are archived but visible below.
        </span>
      </div>

      {/* Filter */}
      <div className="flex items-center justify-between gap-4 border-b border-border pb-3">
        <div className="flex items-center gap-1.5 overflow-x-auto">
          {(["all", "successful", "errors"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded text-xs font-semibold capitalize transition-all cursor-pointer ${
                filter === f
                  ? "bg-accent text-foreground border border-border"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Submissions Table Container (styled like Leaderboard Card) */}
      <div className="nexus-card overflow-x-auto">
        <Table>
          <TableHeader className="bg-muted border-b border-border">
            <TableRow className="hover:bg-transparent border-b-border">
              <TableHead className="w-12 text-muted-foreground font-medium text-[11px] text-center">#</TableHead>
              <TableHead className="text-muted-foreground font-medium text-[11px]">Submission</TableHead>
              <TableHead className="w-28 text-muted-foreground font-medium text-[11px] text-center">Status</TableHead>
              <TableHead className="w-28 text-muted-foreground font-medium text-[11px] text-right">Rating</TableHead>
              <TableHead className="w-24 text-muted-foreground font-medium text-[11px] text-center py-1.5">
                <div>Record</div>
                <div className="text-[9px] font-mono text-muted-foreground/75 font-normal tracking-wider uppercase">(W-L-D)</div>
              </TableHead>
              <TableHead className="w-24 text-muted-foreground font-medium text-[11px] text-center">Uploaded</TableHead>
              <TableHead className="w-28 text-muted-foreground font-medium text-[11px] text-center">Episodes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody ref={tableRef}>
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <TableRow key={idx} className="border-b border-border">
                  <TableCell className="text-center"><Skeleton className="h-4 w-5 mx-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-16 mx-auto rounded-full" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-14 mx-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 mx-auto" /></TableCell>
                  <TableCell><Skeleton className="h-7 w-20 mx-auto rounded-md" /></TableCell>
                </TableRow>
              ))
            ) : (
              filteredSubmissions.map((s, i) => {
                const filename = (s.artifactKey || s.artifact_key || "agent.py").split("/").pop() || "agent.py";
                const createdRaw = s.createdAt || s.created_at;
                const relativeTimeStr = formatRelativeTime(createdRaw);
                const isActive = s.status === "active";
                const isValidated = s.status === "validated";
                const isQueued = s.status === "queued" || s.status === "compiling";
                const isRejected = s.status === "rejected" || s.status === "errored" || s.status === "failed";

                return (
                  <TableRow
                    key={s.id}
                    className={`sub-row-anim opacity-0 border-b border-border hover:bg-muted/50 transition-colors relative ${
                      isActive ? "border-l-4 border-l-emerald-600" : (i === 0 ? "border-l-4 border-l-amber-600" : "")
                    }`}
                  >
                    {/* Index / Rank */}
                    <TableCell className="font-mono text-xs text-center text-muted-foreground font-bold">{i + 1}</TableCell>

                    {/* Submission filename */}
                    <TableCell className="font-mono text-xs font-semibold text-foreground">
                      {filename}
                    </TableCell>

                    {/* Status with markers */}
                    <TableCell className="text-center">
                      {isActive ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-semibold">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
                          <span>Active</span>
                        </span>
                      ) : isValidated ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-[10px] font-mono text-blue-600 dark:text-blue-400 font-semibold">
                          Validated
                        </span>
                      ) : isQueued ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-[10px] font-mono text-amber-600 dark:text-amber-400 font-semibold">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-ping shrink-0" />
                          <span>Queued</span>
                        </span>
                      ) : isRejected ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/20 text-[10px] font-mono text-red-600 dark:text-red-400 font-semibold">
                          Rejected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-muted border border-border text-[10px] font-mono text-muted-foreground font-semibold">
                          {s.status}
                        </span>
                      )}
                    </TableCell>

                    {/* Rating (Plain text like Leaderboard) */}
                    <TableCell className="font-mono text-xs font-bold text-right text-foreground">
                      {typeof s.rating === "number" ? s.rating.toFixed(1) : "—"}
                    </TableCell>

                    {/* Record (W-L-D) */}
                    <TableCell className="font-mono text-xs text-center text-muted-foreground">
                      {typeof s.wins === "number" ? `${s.wins}-${s.losses ?? 0}-${s.draws ?? 0}` : "0-0-0"}
                    </TableCell>

                    {/* Uploaded Relative Time */}
                    <TableCell className="font-mono text-[11px] text-center text-muted-foreground">
                      {relativeTimeStr}
                    </TableCell>

                    {/* Episodes Action Button */}
                    <TableCell className="text-center">
                      <Link
                        href={`/replay?submissionId=${s.id}&artifact=${encodeURIComponent(filename)}`}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-muted hover:bg-primary/10 border border-border hover:border-primary/40 text-xs font-medium text-foreground hover:text-primary transition-all cursor-pointer active:scale-95"
                        title={`Watch episodes for ${filename}`}
                      >
                        <Play className="w-3 h-3 fill-current text-primary" />
                        <span>Episodes</span>
                      </Link>
                    </TableCell>
                  </TableRow>
                );
              })
            )}

            {!loading && filteredSubmissions.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="text-center py-12 text-xs font-mono text-muted-foreground uppercase"
                >
                  NO SUBMISSIONS RECORDED YET
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
