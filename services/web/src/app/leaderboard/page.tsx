"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { RefreshCw, Search, Download, Play } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/auth-client";
import { clientCache } from "@/lib/client-cache";
import { animate } from "animejs";

import { Skeleton } from "@/components/ui/skeleton";

interface LeaderboardEntry {
  teamId: string;
  teamName: string;
  rating: number;
  rd: number;
  wins: number;
  losses: number;
  draws: number;
  matchesPlayed: number;
  lastActivityAt?: string | null;
  bestSubmissionId?: string | null;
  members?: { name: string; image?: string | null }[];
}

function formatRelativeTime(dateInput: Date | string | number | null | undefined): string {
  if (!dateInput) return "Never";
  const date = typeof dateInput === "string" || typeof dateInput === "number" ? new Date(dateInput) : dateInput;
  if (isNaN(date.getTime())) return "Never";
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

export default function LeaderboardPage() {
  const { data: session } = useSession();
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [autoRefreshing, setAutoRefreshing] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const tableRef = useRef<HTMLTableSectionElement>(null);

  // Initial fetch and manual reload handler
  useEffect(() => {
    let isCurrent = true;

    // Load from clientCache after mounting to prevent SSR hydration mismatch
    const cached = clientCache.getLeaderboard();
    if (cached && cached.length > 0) {
      Promise.resolve().then(() => {
        if (isCurrent) {
          setEntries(cached);
          setLoading(false);
        }
      });
    }

    const headers: Record<string, string> = {};
    if (session?.token) headers["Authorization"] = `Bearer ${session.token}`;

    fetch("/api/leaderboard", { headers })
      .then((res) => {
        if (!res.ok) throw new Error("Fetch failed");
        return res.json();
      })
      .then((data: LeaderboardEntry[]) => {
        if (isCurrent) {
          clientCache.setLeaderboard(data);
          setEntries(data);
          setLoading(false);
          setAutoRefreshing(false);
        }
      })
      .catch(() => {
        if (isCurrent) {
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
    const fetchQuietly = () => {
      if (document.visibilityState !== "visible") return;
      setAutoRefreshing(true);
      const headers: Record<string, string> = {};
      if (session?.token) headers["Authorization"] = `Bearer ${session.token}`;

      fetch("/api/leaderboard", { headers })
        .then((res) => (res.ok ? res.json() : null))
        .then((data: LeaderboardEntry[] | null) => {
          if (data) setEntries(data);
        })
        .finally(() => setAutoRefreshing(false));
    };

    const interval = setInterval(fetchQuietly, 12000);

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
  }, [session]);

  const refreshLeaderboard = () => {
    setLoading(true);
    setReloadToken((t) => t + 1);
  };

  const exportCSV = () => {
    const header = "Rank,Team,Rating,RD,Wins,Losses,Draws,Matches Played\n";
    const rows = entries.map((e, i) =>
      `${i + 1},"${e.teamName}",${e.rating},${e.rd},${e.wins},${e.losses},${e.draws},${e.matchesPlayed}`
    ).join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "nexus-wars-leaderboard.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const filteredEntries = entries.filter((e) =>
    e.teamName.toLowerCase().includes(searchQuery.toLowerCase())
  );

  useEffect(() => {
    if (!loading && filteredEntries.length > 0 && tableRef.current) {
      animate(tableRef.current.querySelectorAll(".table-row-anim"), {
        opacity: [0, 1],
        translateX: [-8, 0],
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delay: (_el: any, i = 0) => i * 35,
        duration: 400,
        ease: "outQuint",
      });
    }
  }, [loading, filteredEntries]);

  return (
    <div className="space-y-5">
      {/* Top Action Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold text-foreground tracking-tight">Leaderboard</h2>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={exportCSV}
            disabled={loading || entries.length === 0}
            className="nexus-pill bg-muted border-border text-foreground hover:bg-accent text-xs"
          >
            <Download className="w-3.5 h-3.5" />
            Raw Data
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={loading || autoRefreshing}
            onClick={refreshLeaderboard}
            className="nexus-pill bg-muted border-border text-foreground hover:bg-accent text-xs cursor-pointer active:scale-95"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading || autoRefreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Search Input Bar */}
      <div className="relative max-w-full">
        <Search className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search teams"
          className="w-full h-10 pl-11 pr-4 bg-card hover:bg-muted focus:bg-card border border-border focus:border-primary rounded-lg text-xs text-foreground placeholder:text-muted-foreground outline-none transition-all"
        />
      </div>

      {/* Leaderboard Table Container */}
      <div className="nexus-card overflow-x-auto">
        <Table>
          <TableHeader className="bg-muted border-b border-border">
            <TableRow className="hover:bg-transparent border-b-border">
              <TableHead className="w-12 text-muted-foreground font-medium text-[11px] text-center">#</TableHead>
              <TableHead className="text-muted-foreground font-medium text-[11px]">Team</TableHead>
              <TableHead className="w-24 text-muted-foreground font-medium text-[11px] text-center">Members</TableHead>
              <TableHead className="w-28 text-muted-foreground font-medium text-[11px] text-right">Rating</TableHead>
              <TableHead className="w-24 text-muted-foreground font-medium text-[11px] text-center py-1.5">
                <div>Record</div>
                <div className="text-[9px] font-mono text-muted-foreground/75 font-normal tracking-wider uppercase">(W-L-D)</div>
              </TableHead>
              <TableHead className="w-24 text-muted-foreground font-medium text-[11px] text-center">Last</TableHead>
              <TableHead className="w-28 text-muted-foreground font-medium text-[11px] text-center">Episodes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody ref={tableRef}>
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <TableRow key={idx} className="border-b border-border">
                  <TableCell className="text-center"><Skeleton className="h-4 w-5 mx-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-12 mx-auto rounded-full" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16 mx-auto" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12 mx-auto" /></TableCell>
                  <TableCell><Skeleton className="h-7 w-20 mx-auto rounded-md" /></TableCell>
                </TableRow>
              ))
            ) : (
              filteredEntries.map((e, i) => {
                const isTop3 = i < 3;
                const relativeTimeStr = formatRelativeTime(e.lastActivityAt);

                return (
                  <TableRow
                    key={e.teamId}
                    className={`table-row-anim opacity-0 border-b border-border hover:bg-muted/50 transition-colors relative ${
                      isTop3 ? "border-l-4 border-l-amber-600" : ""
                    }`}
                  >
                    {/* Rank */}
                    <TableCell className="font-mono text-xs text-center text-muted-foreground font-bold">{i + 1}</TableCell>

                    {/* Team */}
                    <TableCell className="font-sans text-xs font-semibold text-foreground">{e.teamName}</TableCell>

                    {/* Members */}
                    <TableCell className="text-center">
                      <div className="flex items-center justify-center -space-x-1.5">
                        {(e.members || []).map((m, idx) => (
                          /* eslint-disable-next-line @next/next/no-img-element */
                          <img
                            key={idx}
                            src={m.image || `https://api.dicebear.com/7.x/identicon/svg?seed=${encodeURIComponent(m.name)}`}
                            alt={m.name}
                            className="w-6 h-6 rounded-full border border-background object-cover"
                            title={m.name}
                          />
                        ))}
                      </div>
                    </TableCell>

                    {/* Rating */}
                    <TableCell className="font-mono text-xs font-bold text-right text-foreground">
                      {e.rating.toFixed(1)}
                    </TableCell>

                    {/* Record (W-L-D) */}
                    <TableCell className="font-mono text-xs text-center text-muted-foreground">
                      {e.wins}-{e.losses}-{e.draws}
                    </TableCell>

                    {/* Last activity */}
                    <TableCell className="font-mono text-[11px] text-center text-muted-foreground">
                      {relativeTimeStr}
                    </TableCell>

                    {/* View Episodes action button */}
                    <TableCell className="text-center">
                      <Link
                        href={`/replay?teamId=${e.teamId}&submissionId=${e.bestSubmissionId || ""}&teamName=${encodeURIComponent(e.teamName)}`}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-muted hover:bg-primary/10 border border-border hover:border-primary/40 text-xs font-medium text-foreground hover:text-primary transition-all cursor-pointer active:scale-95"
                        title={`Watch episodes for ${e.teamName}`}
                      >
                        <Play className="w-3 h-3 fill-current text-primary" />
                        <span>Episodes</span>
                      </Link>
                    </TableCell>
                  </TableRow>
                );
              })
            )}

            {!loading && filteredEntries.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="text-center py-12 text-xs font-mono text-muted-foreground uppercase"
                >
                  NO RANKED TEAMS RECORDED YET
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

