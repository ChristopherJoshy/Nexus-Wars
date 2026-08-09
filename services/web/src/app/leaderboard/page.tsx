"use client";

import { useEffect, useState, useRef } from "react";
import { RefreshCw, Search, Download, Timer, FileText, X, CheckCircle } from "lucide-react";
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
import { animate } from "animejs";
import { Skeleton } from "@/components/ui/skeleton";

interface LeaderboardEntry {
  teamId: string;
  teamName: string;
  collegeName?: string | null;
  teamMembersInfo?: string | null;
  mobileNumbers?: string | null;
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

  // 30-Minute Closing Countdown Timer State (1800 seconds)
  const [timeLeft, setTimeLeft] = useState<number>(1800);

  // Modal State for Top 10 Team Registration
  const [selectedTeam, setSelectedTeam] = useState<{ id: string; name: string; college: string; membersInfo: string; phones: string } | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [savingDetails, setSavingDetails] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const tableRef = useRef<HTMLTableSectionElement>(null);

  // 30-minute countdown timer effect
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTimer = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const fetchLeaderboard = async () => {
    try {
      const res = await fetch("/api/leaderboard");
      if (res.ok) {
        const data = await res.json();
        setEntries(data);
      }
    } catch (err) {
      console.error("Failed to fetch leaderboard", err);
    } finally {
      setLoading(false);
      setAutoRefreshing(false);
    }
  };

  useEffect(() => {
    fetchLeaderboard();
    const interval = setInterval(() => {
      setAutoRefreshing(true);
      fetchLeaderboard();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const refreshLeaderboard = () => {
    setAutoRefreshing(true);
    fetchLeaderboard();
  };

  const openFormModal = (entry: LeaderboardEntry) => {
    setSelectedTeam({
      id: entry.teamId,
      name: entry.teamName,
      college: entry.collegeName || "",
      membersInfo: entry.teamMembersInfo || "",
      phones: entry.mobileNumbers || "",
    });
    setSaveError(null);
    setSaveSuccess(false);
    setModalOpen(true);
  };

  const saveRegistrationDetails = async () => {
    if (!selectedTeam || !session) return;
    setSavingDetails(true);
    setSaveError(null);
    try {
      const res = await fetch("/api/teams", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.token}`,
        },
        body: JSON.stringify({
          teamId: selectedTeam.id,
          collegeName: selectedTeam.college,
          teamMembersInfo: selectedTeam.membersInfo,
          mobileNumbers: selectedTeam.phones,
        }),
      });

      if (res.ok) {
        setSaveSuccess(true);
        setTimeout(() => {
          setModalOpen(false);
          setSaveSuccess(false);
          refreshLeaderboard();
        }, 1200);
      } else {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || "Failed to save team registration details.");
      }
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Error saving details.");
    } finally {
      setSavingDetails(false);
    }
  };

  const exportCSV = () => {
    if (entries.length === 0) return;
    const headers = ["Rank", "Team Name", "College Name", "Team Members", "Mobile Numbers", "Rating", "RD", "Wins", "Losses", "Draws", "Matches Played"];
    const rows = entries.map((e, index) => [
      index + 1,
      `"${e.teamName.replace(/"/g, '""')}"`,
      `"${(e.collegeName || "").replace(/"/g, '""')}"`,
      `"${(e.teamMembersInfo || "").replace(/"/g, '""')}"`,
      `"${(e.mobileNumbers || "").replace(/"/g, '""')}"`,
      e.rating.toFixed(1),
      e.rd.toFixed(1),
      e.wins,
      e.losses,
      e.draws,
      e.matchesPlayed,
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "nexus-wars-leaderboard-export.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filteredEntries = entries.filter((e) => {
    const query = searchQuery.toLowerCase();
    const teamMatch = e.teamName?.toLowerCase().includes(query) ?? false;
    const memberMatch = e.members?.some((m) => m.name?.toLowerCase().includes(query)) ?? false;
    return teamMatch || memberMatch;
  });

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
      {/* 30-Minute Closing Countdown Banner */}
      <div className="bg-gradient-to-r from-amber-500/20 via-primary/20 to-amber-500/20 border border-amber-500/40 rounded-xl p-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-amber-300 font-mono shadow-lg">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-amber-500/20 border border-amber-500/40">
            <Timer className="w-5 h-5 animate-pulse text-amber-400" />
          </div>
          <div>
            <h3 className="font-bold uppercase tracking-wider text-xs text-foreground flex items-center gap-2">
              Final Event Closing Sprint
              <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 font-semibold uppercase tracking-wider">
                Active
              </span>
            </h3>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Event closes soon. Top 10 teams must complete their college & contact registration details.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-black/60 border border-amber-500/50 px-4 py-2 rounded-lg shadow-inner">
          <span className="text-[10px] text-amber-400/80 uppercase tracking-widest font-semibold">Closing In:</span>
          <span className="font-bold text-xl text-amber-400 tracking-widest font-mono">
            {formatTimer(timeLeft)}
          </span>
        </div>
      </div>

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
            className="nexus-pill bg-muted border-border text-foreground hover:bg-accent text-xs cursor-pointer active:scale-95"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
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
          placeholder="Search teams or players"
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
              <TableHead className="w-36 text-muted-foreground font-medium text-[11px] text-center">Registration</TableHead>
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
                  <TableCell><Skeleton className="h-7 w-24 mx-auto rounded-md" /></TableCell>
                </TableRow>
              ))
            ) : (
              filteredEntries.map((e, i) => {
                const isTop3 = i < 3;
                const isTop10 = i < 10;
                const relativeTimeStr = formatRelativeTime(e.lastActivityAt);
                const hasRegistration = Boolean(e.collegeName && e.teamMembersInfo && e.mobileNumbers);

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

                    {/* Registration Form Button (ONLY FOR TOP 10 TEAMS) */}
                    <TableCell className="text-center">
                      {isTop10 ? (
                        <button
                          onClick={() => openFormModal(e)}
                          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded text-xs font-semibold transition-all cursor-pointer active:scale-95 ${
                            hasRegistration
                              ? "bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/40 text-emerald-400"
                              : "bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/40 text-amber-400"
                          }`}
                        >
                          <FileText className="w-3.5 h-3.5" />
                          <span>{hasRegistration ? "Edit Details" : "Team Form"}</span>
                        </button>
                      ) : (
                        <span className="text-[11px] text-muted-foreground font-mono">—</span>
                      )}
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
                  No teams found matching search criteria.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Top 10 Team Registration Form Modal */}
      {modalOpen && selectedTeam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4">
          <div className="bg-card border border-border rounded-xl p-6 max-w-lg w-full space-y-4 shadow-2xl relative">
            <button
              onClick={() => setModalOpen(false)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground p-1 rounded-lg hover:bg-muted transition-all"
            >
              <X className="w-5 h-5" />
            </button>

            <div>
              <h3 className="text-lg font-bold text-foreground">Top 10 Team Registration</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Team: <span className="font-semibold text-primary">{selectedTeam.name}</span>
              </p>
            </div>

            {saveSuccess && (
              <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 p-3 rounded-lg text-xs font-mono flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                Team registration details saved successfully!
              </div>
            )}

            {saveError && (
              <div className="bg-destructive/10 border border-destructive/30 text-destructive p-3 rounded-lg text-xs font-mono">
                {saveError}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-mono text-muted-foreground uppercase mb-1">
                  College / Institution Name
                </label>
                <input
                  type="text"
                  value={selectedTeam.college}
                  onChange={(e) => setSelectedTeam({ ...selectedTeam, college: e.target.value })}
                  placeholder="e.g. National Institute of Technology"
                  className="w-full bg-muted border border-border focus:border-primary p-2.5 rounded-lg text-xs text-foreground outline-none font-medium"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-muted-foreground uppercase mb-1">
                  Team Members Names
                </label>
                <textarea
                  rows={2}
                  value={selectedTeam.membersInfo}
                  onChange={(e) => setSelectedTeam({ ...selectedTeam, membersInfo: e.target.value })}
                  placeholder="e.g. Christopher Joshy, Karthik, Alex"
                  className="w-full bg-muted border border-border focus:border-primary p-2.5 rounded-lg text-xs text-foreground outline-none font-medium resize-none"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-muted-foreground uppercase mb-1">
                  Mobile Phone Numbers
                </label>
                <input
                  type="text"
                  value={selectedTeam.phones}
                  onChange={(e) => setSelectedTeam({ ...selectedTeam, phones: e.target.value })}
                  placeholder="e.g. +91 9876543210, +91 9123456789"
                  className="w-full bg-muted border border-border focus:border-primary p-2.5 rounded-lg text-xs text-foreground outline-none font-medium"
                />
              </div>
            </div>

            <div className="pt-2 flex justify-end gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setModalOpen(false)}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={saveRegistrationDetails}
                loading={savingDetails}
                disabled={savingDetails || !selectedTeam.college || !selectedTeam.membersInfo || !selectedTeam.phones}
                className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-5 text-xs"
              >
                Save Details
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
