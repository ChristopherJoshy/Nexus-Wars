"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { CheckCircle2, AlertTriangle, Upload, Zap, Clock, Tv } from "lucide-react";
import { useSession, signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
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
}

interface SubmissionsResponse {
  submissions: Submission[];
  totalCount: number;
  maxSubmissions: number;
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
  const [filter, setFilter] = useState<"all" | "successful" | "errors">("all");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasTeam, setHasTeam] = useState<boolean | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!session) return;

    fetch("/api/teams", {
      headers: { Authorization: `Bearer ${session.token}` },
    })
      .then((res) => {
        if (res.ok) {
          setHasTeam(true);
          return fetch("/api/submissions", {
            headers: { Authorization: `Bearer ${session.token}` },
          });
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
        if (data) {
          setSubmissions(data.submissions || []);
          setTotalCount(data.totalCount ?? 0);
          setMaxSubmissions(data.maxSubmissions ?? 5);
        }
      })
      .catch(() => {
        setSubmissions([]);
      });
  }, [session]);

  useEffect(() => {
    if (submissions.length > 0 && listRef.current) {
      animate(listRef.current.querySelectorAll(".sub-row-anim"), {
        opacity: [0, 1],
        translateY: [6, 0],
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delay: (_el: any, i = 0) => i * 30,
        duration: 450,
        ease: "outQuint",
      });
    }
  }, [submissions]);

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
    const isErr = s.status === "error" || s.status === "failed" || s.status === "rejected";
    if (filter === "successful") return !isErr;
    if (filter === "errors") return isErr;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Cap Info + Upload */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-foreground">Submissions</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Upload Python bots to compete on the live ladder.
          </p>
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
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground font-sans font-semibold text-xs shadow-xs transition-all cursor-pointer ${
              totalCount >= maxSubmissions ? "opacity-50 pointer-events-none" : ""
            }`}
          >
            <Upload className="w-4 h-4" />
            <span>{uploading ? "Uploading..." : "Upload Bot (.py)"}</span>
          </label>
        </div>
      </div>

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

      {/* Submissions List */}
      <div className="nexus-card overflow-x-auto">
        <div className="px-5 py-3 border-b border-border bg-muted flex items-center justify-between text-muted-foreground text-[11px] font-medium">
          <span>Submission</span>
          <div className="flex items-center gap-8">
            <span>Status</span>
            <span>Episodes</span>
          </div>
        </div>

        <div ref={listRef} className="divide-y divide-border">
          {filteredSubmissions.map((s) => {
            const isError = s.status === "error" || s.status === "failed" || s.status === "rejected" || s.status === "errored";
            const isActive = s.status === "active";
            const filename = (s.artifactKey || s.artifact_key || "agent.py").split("/").pop() || "agent.py";
            const createdRaw = s.createdAt || s.created_at;
            const relativeTimeStr = formatRelativeTime(createdRaw);

            return (
              <div
                key={s.id}
                className="sub-row-anim opacity-0 px-5 py-3.5 flex items-center justify-between hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {isError ? (
                    <AlertTriangle className="w-5 h-5 text-amber-700 shrink-0" />
                  ) : (
                    <CheckCircle2 className={`w-5 h-5 shrink-0 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                  )}

                  <div>
                    <div className="text-xs font-semibold text-foreground font-mono">{filename}</div>
                    <div className="text-[11px] text-muted-foreground font-mono">
                      {s.status} &bull; {relativeTimeStr}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  <span
                    className={`px-2 py-0.5 rounded font-mono text-[10px] uppercase font-bold tracking-wider ${
                      isError
                        ? "bg-amber-100 text-amber-800 border border-amber-300"
                        : isActive
                          ? "bg-primary/10 text-primary border border-primary/30"
                          : "bg-muted text-muted-foreground border border-border"
                    }`}
                  >
                    {s.status}
                  </span>

                  <Link
                    href={`/replay?submissionId=${s.id}&artifact=${encodeURIComponent(filename)}`}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-muted hover:bg-primary/10 border border-border hover:border-primary/40 text-xs font-medium text-foreground hover:text-primary transition-all cursor-pointer"
                    title={`Watch episodes for ${filename}`}
                  >
                    <Tv className="w-3.5 h-3.5 text-primary" />
                    <span>Episodes</span>
                  </Link>
                </div>
              </div>
            );
          })}

          {filteredSubmissions.length === 0 && (
            <div className="text-center py-12 text-xs font-mono text-muted-foreground">
              NO SUBMISSIONS YET
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
