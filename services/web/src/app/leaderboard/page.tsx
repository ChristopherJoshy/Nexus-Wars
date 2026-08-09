"use client";

import { useEffect, useState, useRef } from "react";
import { RefreshCw, Search, Download, Timer, FileText, X, CheckCircle, Lock, Trophy, ShieldAlert, LogIn } from "lucide-react";
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
import Link from "next/link";

interface LeaderboardEntry {
  teamId: string;
  teamName: string;
  hasRegistration?: boolean;
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

interface UserTeamData {
  id: string;
  name: string;
  collegeName?: string | null;
  teamMembersInfo?: string | null;
  mobileNumbers?: string | null;
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

  // Authenticated User's Team Data
  const [myTeam, setMyTeam] = useState<UserTeamData | null>(null);

  // 3-Minute Closing Countdown Timer State (180 seconds)
  const [timeLeft, setTimeLeft] = useState<number>(180);
  const [isFrozen, setIsFrozen] = useState<boolean>(false);

  // Modal State for Team Registration
  const [targetTeam, setTargetTeam] = useState<LeaderboardEntry | null>(null);
  const [formData, setFormData] = useState({ college: "", membersInfo: "", phones: "" });
  const [modalOpen, setModalOpen] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [savingDetails, setSavingDetails] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const tableRef = useRef<HTMLTableSectionElement>(null);

  // 3-minute countdown timer effect & Leaderboard freeze trigger
  useEffect(() => {
    if (timeLeft <= 0) {
      setIsFrozen(true);
      return;
    }
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          setIsFrozen(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [timeLeft]);

  const formatTimer = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // Fetch logged in user's team
  const fetchMyTeam = async () => {
    if (!session?.token) return null;
    try {
      const res = await fetch("/api/teams", {
        headers: { Authorization: `Bearer ${session.token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMyTeam(data);
        return data;
      }
    } catch (err) {
      console.error("Failed to fetch user team", err);
    }
    return null;
  };

  useEffect(() => {
    if (session) {
      fetchMyTeam();
    }
  }, [session]);

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
    if (isFrozen) return;

    const interval = setInterval(() => {
      if (!isFrozen) {
        setAutoRefreshing(true);
        fetchLeaderboard();
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [isFrozen]);

  const refreshLeaderboard = () => {
    if (isFrozen) return;
    setAutoRefreshing(true);
    fetchLeaderboard();
  };

  const handleFormButtonClick = async (entry: LeaderboardEntry) => {
    setTargetTeam(entry);
    setSaveError(null);
    setSaveSuccess(false);

    // If user is not signed in
    if (!session?.user) {
      setAccessDenied(true);
      setModalOpen(true);
      return;
    }

    // Ensure we have user's active team data
    let userTeam = myTeam;
    if (!userTeam) {
      userTeam = await fetchMyTeam();
    }

    // Compare team IDs (robust case-insensitive string comparison)
    const isMemberOfThisTeam = Boolean(
      userTeam && userTeam.id && entry.teamId &&
      String(userTeam.id).toLowerCase().trim() === String(entry.teamId).toLowerCase().trim()
    );

    if (isMemberOfThisTeam && userTeam) {
      setAccessDenied(false);
      setFormData({
        college: userTeam.collegeName || "",
        membersInfo: userTeam.teamMembersInfo || "",
        phones: userTeam.mobileNumbers || "",
      });
    } else {
      setAccessDenied(true);
    }
    setModalOpen(true);
  };

  const saveRegistrationDetails = async () => {
    if (!targetTeam || !session || accessDenied) return;
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
          teamId: targetTeam.teamId,
          collegeName: formData.college,
          teamMembersInfo: formData.membersInfo,
          mobileNumbers: formData.phones,
        }),
      });

      if (res.ok) {
        const updated = await res.json();
        setMyTeam(updated);
        setSaveSuccess(true);
        setTimeout(() => {
          setModalOpen(false);
          setSaveSuccess(false);
          fetchLeaderboard();
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
    const headers = ["Rank", "Team Name", "Rating", "RD", "Wins", "Losses", "Draws", "Matches Played"];
    const rows = entries.map((e, index) => [
      index + 1,
      `"${e.teamName.replace(/"/g, '""')}"`,
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
    link.setAttribute("download", "nexus-wars-leaderboard.csv");
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
    <div className="space-y-6">
      {/* 3-Minute Closing & Frozen Banner */}
      <div className="bg-stone-900 border-2 border-amber-500 rounded-2xl p-5 shadow-2xl flex flex-col sm:flex-row items-center justify-between gap-4 text-stone-100">
        <div className="flex items-center gap-4">
          <div className="p-3 rounded-xl bg-amber-500/20 border border-amber-500/50 shrink-0">
            {isFrozen ? (
              <Trophy className="w-7 h-7 text-amber-400 animate-bounce" />
            ) : (
              <Timer className="w-7 h-7 text-amber-400 animate-pulse" />
            )}
          </div>
          <div>
            <h3 className="font-extrabold uppercase tracking-wider text-sm sm:text-base text-amber-400 flex items-center gap-2">
              {isFrozen ? "🏆 EVENT CONCLUDED — LEADERBOARD FROZEN" : "⚡ 3-MINUTE FINAL SPRINT"}
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold uppercase tracking-wider ${
                isFrozen
                  ? "bg-emerald-500 text-stone-950"
                  : "bg-amber-500 text-stone-950 animate-pulse"
              }`}>
                {isFrozen ? "FINAL STANDINGS" : "LIVE SPRINT"}
              </span>
            </h3>
            <p className="text-xs text-stone-300 font-medium mt-1">
              {isFrozen
                ? "Matchmaking has ended and the leaderboard is permanently frozen. Top 10 teams must complete their registration details below."
                : "Matchmaking ends in 3 minutes! Top 10 teams must submit their college name, team members, and mobile numbers."}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 bg-black/90 border-2 border-amber-400/80 px-5 py-2.5 rounded-xl shadow-inner shrink-0">
          <span className="text-xs text-amber-300/90 uppercase tracking-widest font-bold font-mono">
            {isFrozen ? "STATUS:" : "TIMER:"}
          </span>
          <span className={`font-black text-2xl sm:text-3xl tracking-widest font-mono ${
            isFrozen ? "text-emerald-400" : "text-amber-400"
          }`}>
            {isFrozen ? "FROZEN" : formatTimer(timeLeft)}
          </span>
        </div>
      </div>

      {/* Top Action Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-black text-foreground tracking-tight">Leaderboard</h2>
          {isFrozen && (
            <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-amber-500/20 border border-amber-500/40 text-amber-500">
              [ LOCKED & FROZEN ]
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={exportCSV}
            disabled={loading || entries.length === 0}
            className="nexus-pill bg-card border-border text-foreground hover:bg-accent text-xs cursor-pointer active:scale-95 font-semibold"
          >
            <Download className="w-3.5 h-3.5 mr-1" />
            Raw Data
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={loading || autoRefreshing || isFrozen}
            onClick={refreshLeaderboard}
            className="nexus-pill bg-card border-border text-foreground hover:bg-accent text-xs cursor-pointer active:scale-95 font-semibold disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading || autoRefreshing ? "animate-spin" : ""}`} />
            {isFrozen ? "Frozen" : "Refresh"}
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
          className="w-full h-10 pl-11 pr-4 bg-card hover:bg-muted focus:bg-card border border-border focus:border-primary rounded-lg text-xs text-foreground placeholder:text-muted-foreground outline-none transition-all font-medium"
        />
      </div>

      {/* Leaderboard Table Container */}
      <div className="nexus-card overflow-x-auto border border-border rounded-xl shadow-md">
        <Table>
          <TableHeader className="bg-muted/80 border-b border-border">
            <TableRow className="hover:bg-transparent border-b-border">
              <TableHead className="w-12 text-muted-foreground font-bold text-xs text-center">#</TableHead>
              <TableHead className="text-muted-foreground font-bold text-xs">Team</TableHead>
              <TableHead className="w-24 text-muted-foreground font-bold text-xs text-center">Members</TableHead>
              <TableHead className="w-28 text-muted-foreground font-bold text-xs text-right">Rating</TableHead>
              <TableHead className="w-24 text-muted-foreground font-bold text-xs text-center py-2">
                <div>Record</div>
                <div className="text-[9px] font-mono text-muted-foreground font-semibold tracking-wider uppercase">(W-L-D)</div>
              </TableHead>
              <TableHead className="w-24 text-muted-foreground font-bold text-xs text-center">Last</TableHead>
              <TableHead className="w-36 text-muted-foreground font-bold text-xs text-center">Registration</TableHead>
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
                const hasRegistration = Boolean(e.hasRegistration);

                return (
                  <TableRow
                    key={e.teamId}
                    className={`table-row-anim opacity-0 border-b border-border hover:bg-muted/50 transition-colors relative ${
                      isTop3 ? "border-l-4 border-l-amber-500 bg-amber-500/5" : ""
                    }`}
                  >
                    {/* Rank */}
                    <TableCell className="font-mono text-xs text-center text-foreground font-extrabold">{i + 1}</TableCell>

                    {/* Team */}
                    <TableCell className="font-sans text-xs font-bold text-foreground">{e.teamName}</TableCell>

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
                    <TableCell className="font-mono text-xs font-black text-right text-primary">
                      {e.rating.toFixed(1)}
                    </TableCell>

                    {/* Record (W-L-D) */}
                    <TableCell className="font-mono text-xs text-center font-bold text-muted-foreground">
                      {e.wins}-{e.losses}-{e.draws}
                    </TableCell>

                    {/* Last activity */}
                    <TableCell className="font-mono text-[11px] text-center text-muted-foreground font-semibold">
                      {relativeTimeStr}
                    </TableCell>

                    {/* Registration Form Button */}
                    <TableCell className="text-center">
                      {isTop10 ? (
                        <button
                          onClick={() => handleFormButtonClick(e)}
                          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold shadow-sm transition-all cursor-pointer active:scale-95 ${
                            hasRegistration
                              ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                              : "bg-amber-600 hover:bg-amber-700 text-white"
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

      {/* Registration Form / Access Control Modal */}
      {modalOpen && targetTeam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4">
          <div className="bg-stone-900 border-2 border-amber-500 rounded-2xl p-6 max-w-lg w-full space-y-5 shadow-2xl relative text-stone-100">
            <button
              onClick={() => setModalOpen(false)}
              className="absolute top-4 right-4 text-stone-400 hover:text-white p-1 rounded-lg hover:bg-stone-800 transition-all cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            <div>
              <h3 className="text-xl font-black text-amber-400 flex items-center gap-2">
                <FileText className="w-5 h-5" />
                Top 10 Team Registration
              </h3>
              <p className="text-xs text-stone-300 mt-1 font-medium">
                Team Name: <span className="font-bold text-white uppercase text-sm">{targetTeam.teamName}</span>
              </p>
            </div>

            {/* Privacy Access Control Check */}
            {accessDenied ? (
              <div className="space-y-4 py-2">
                {!session?.user ? (
                  <div className="bg-amber-950/90 border-2 border-amber-500/80 text-amber-200 p-4 rounded-xl text-xs space-y-3 shadow-inner">
                    <div className="flex items-center gap-2 font-black text-amber-400 text-sm">
                      <LogIn className="w-5 h-5 text-amber-400 shrink-0" />
                      <span>Sign In Required</span>
                    </div>
                    <p className="leading-relaxed text-xs text-stone-200 font-medium">
                      Please sign in to your account to view or edit <strong className="text-white uppercase font-bold">{targetTeam.teamName}</strong>&apos;s registration details.
                    </p>
                  </div>
                ) : (
                  <div className="bg-amber-950/90 border-2 border-amber-500/80 text-amber-200 p-4 rounded-xl text-xs space-y-3 shadow-inner">
                    <div className="flex items-center gap-2 font-black text-amber-400 text-sm">
                      <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0" />
                      <span>Access Restricted (Privacy Protected)</span>
                    </div>
                    <p className="leading-relaxed text-xs text-stone-200 font-medium">
                      You are logged in as a member of <strong className="text-amber-400 uppercase font-bold">{myTeam?.name || "another team"}</strong>.
                    </p>
                    <p className="leading-relaxed text-xs text-stone-300">
                      Only authenticated members of <strong className="text-white uppercase font-bold">{targetTeam.teamName}</strong> are authorized to view or edit their team&apos;s details.
                    </p>
                  </div>
                )}

                <div className="flex justify-end gap-3">
                  <Button
                    size="sm"
                    onClick={() => setModalOpen(false)}
                    className="bg-stone-800 hover:bg-stone-700 text-white font-bold px-5 text-xs"
                  >
                    Close
                  </Button>
                </div>
              </div>
            ) : (
              <>
                {saveSuccess && (
                  <div className="bg-emerald-950 border border-emerald-500 text-emerald-300 p-3 rounded-lg text-xs font-mono flex items-center gap-2 font-bold">
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                    Team registration details saved successfully!
                  </div>
                )}

                {saveError && (
                  <div className="bg-red-950 border border-red-500 text-red-300 p-3 rounded-lg text-xs font-mono font-bold">
                    {saveError}
                  </div>
                )}

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-mono font-bold text-amber-400 uppercase mb-1.5">
                      College / Institution Name
                    </label>
                    <input
                      type="text"
                      value={formData.college}
                      onChange={(e) => setFormData({ ...formData, college: e.target.value })}
                      placeholder="e.g. National Institute of Technology"
                      className="w-full bg-stone-800 border border-stone-700 focus:border-amber-400 p-3 rounded-xl text-xs text-white placeholder:text-stone-500 outline-none font-medium"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-mono font-bold text-amber-400 uppercase mb-1.5">
                      Team Members Names
                    </label>
                    <textarea
                      rows={2}
                      value={formData.membersInfo}
                      onChange={(e) => setFormData({ ...formData, membersInfo: e.target.value })}
                      placeholder="e.g. Christopher Joshy, Karthik, Alex"
                      className="w-full bg-stone-800 border border-stone-700 focus:border-amber-400 p-3 rounded-xl text-xs text-white placeholder:text-stone-500 outline-none font-medium resize-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-mono font-bold text-amber-400 uppercase mb-1.5">
                      Mobile Phone Numbers
                    </label>
                    <input
                      type="text"
                      value={formData.phones}
                      onChange={(e) => setFormData({ ...formData, phones: e.target.value })}
                      placeholder="e.g. +91 9876543210, +91 9123456789"
                      className="w-full bg-stone-800 border border-stone-700 focus:border-amber-400 p-3 rounded-xl text-xs text-white placeholder:text-stone-500 outline-none font-medium"
                    />
                  </div>
                </div>

                <div className="pt-3 flex justify-end gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setModalOpen(false)}
                    className="bg-stone-800 hover:bg-stone-700 text-stone-200 border-stone-700 text-xs font-semibold"
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    onClick={saveRegistrationDetails}
                    loading={savingDetails}
                    disabled={savingDetails || !formData.college || !formData.membersInfo || !formData.phones}
                    className="nexus-pill bg-amber-500 hover:bg-amber-400 text-stone-950 font-black px-6 text-xs shadow-lg disabled:opacity-50 cursor-pointer"
                  >
                    Save Details
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
