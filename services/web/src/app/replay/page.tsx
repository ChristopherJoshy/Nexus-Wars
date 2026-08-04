"use client";

import { useEffect, useState, useRef, useMemo, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Filter,
  Trophy,
  RotateCcw,
  SkipBack,
  SkipForward,
  Play,
  Pause,
  Copy,
  Check,
  Download,
  Monitor,
  Bot,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ReplayRenderer } from "@/components/replay/ReplayRenderer";
import { useSession } from "@/lib/auth-client";
import { clientCache } from "@/lib/client-cache";
import { animate } from "animejs";
import { formatRelativeTime, useTick } from "@/lib/time";
import JSZip from "jszip";

interface MatchItem {
  id: string;
  seed: number;
  kind: string;
  status: string;
  teamA: string;
  teamB: string;
  teamAImage?: string | null;
  teamBImage?: string | null;
  teamARating: number;
  teamBRating: number;
  teamAChange?: number;
  teamBChange?: number;
  winner: "a" | "b" | "draw";
  winnerName: string | null;
  scores: number[];
  createdAt: string;
  finishedAt: string | null;
  submissionAId?: string;
  submissionBId?: string;
}

interface StepData {
  observation: {
    planets: number[][];
    fleets: number[][];
    player: number;
    step: number;
  };
  action: number[][][];
  reward: number[];
  status: string[];
}

interface ReplayData {
  version: string;
  engine: string;
  seed: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  configuration: any;
  players: { playerId: number }[];
  steps: StepData[];
  info: {
    winner: number | null;
    reason: string;
    scores: number[];
    durationMs: number;
    steps: number;
  };
}

function GameHistoryContent() {
  const { data: session } = useSession();
  const searchParams = useSearchParams();
  
  const teamId = searchParams.get("teamId");
  const teamNameParam = searchParams.get("teamName");
  const submissionId = searchParams.get("submissionId");
  const artifactParam = searchParams.get("artifact");

  const [matchList, setMatchList] = useState<MatchItem[]>([]);
  const [loadingMatches, setLoadingMatches] = useState(true);
  const [selectedMatch, setSelectedMatch] = useState<MatchItem | null>(null);
  const [replay, setReplay] = useState<ReplayData | null>(null);

  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speedMultiplier, setSpeedMultiplier] = useState<0.5 | 1 | 2 | 4>(1);
  const [copied, setCopied] = useState(false);
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState("");

  const handleDownloadAll = async () => {
    if (matchList.length === 0 || downloadingZip) return;
    setDownloadingZip(true);
    setDownloadProgress("0%");
    
    try {
      const zip = new JSZip();
      
      // Cap at 50 most recent replays to prevent memory exhaustion & browser crashes
      const targets = matchList.slice(0, 50);
      const total = targets.length;
      let completed = 0;

      // Batch requests (5 at a time) to prevent network socket / serverless function exhaustion
      const batchSize = 5;
      for (let i = 0; i < targets.length; i += batchSize) {
        const batch = targets.slice(i, i + batchSize);
        
        await Promise.all(
          batch.map(async (m) => {
            try {
              let data = clientCache.getReplay(m.id);
              if (!data) {
                const res = await fetch(`/api/replays/${m.id}`);
                if (res.ok) {
                  const { url } = await res.json();
                  if (url) {
                    const replayRes = await fetch(url);
                    if (replayRes.ok) {
                      data = await replayRes.json();
                      if (data && !data.error) {
                        clientCache.setReplay(m.id, data);
                      }
                    }
                  }
                }
              }
              if (data && !data.error) {
                zip.file(`replay_${m.id}.json`, JSON.stringify(data));
              }
            } catch (e) {
              console.error(`Failed to fetch replay ${m.id}`, e);
            } finally {
              completed++;
              setDownloadProgress(`${Math.round((completed / total) * 100)}%`);
            }
          })
        );
      }
      
      const blob = await zip.generateAsync({
        type: "blob",
        compression: "DEFLATE",
        compressionOptions: { level: 6 }
      });

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `nexus-wars-replays-${submissionId || teamId || "all"}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Failed to generate zip", e);
    } finally {
      setDownloadingZip(false);
      setDownloadProgress("");
    }
  };

  // Responsive canvas size
  const [canvasDim, setCanvasDim] = useState(580);
  const canvasContainerRef = useRef<HTMLDivElement>(null);

  // Re-render every second to keep relative time labels fresh
  useTick(1000);

  // Telemetry Controls
  const [showFleetNum, setShowFleetNum] = useState(true);
  const [showProduction, setShowProduction] = useState(true);
  const [showTrajectories, setShowTrajectories] = useState(false);
  const [fleetSizeFilter, setFleetSizeFilter] = useState<"all" | "small" | "medium" | "large">("all");

  const sidebarRef = useRef<HTMLDivElement>(null);

  const selectMatch = (m: MatchItem) => {
    setSelectedMatch(m);
    setStep(0);
    setPlaying(false);
  };

  // ResizeObserver to calculate maximum available square dimension for canvas
  useEffect(() => {
    const el = canvasContainerRef.current;
    if (!el) return;

    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      const available = Math.max(320, Math.min(rect.width - 24, rect.height - 24));
      setCanvasDim(Math.floor(available));
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Fetch Game History Match List (with client cache for 15s)
  useEffect(() => {
    const cacheKey = submissionId ? `sub:${submissionId}` : teamId ? `team:${teamId}` : "all";
    const cached = clientCache.getMatchList(cacheKey);
    if (cached && cached.length > 0) {
      Promise.resolve().then(() => {
        setMatchList(cached);
        if (cached.length > 0) {
          let targetMatch = cached[0];
          if (submissionId) {
            const found = cached.find((m) => m.submissionAId === submissionId || m.submissionBId === submissionId);
            if (found) targetMatch = found;
          }
          setSelectedMatch(targetMatch);
        } else {
          setSelectedMatch(null);
        }
        setLoadingMatches(false);
      });
      return;
    }

    let url = "/api/replays";
    const queryParts: string[] = [];
    if (teamId) queryParts.push(`teamId=${encodeURIComponent(teamId)}`);
    if (submissionId) queryParts.push(`submissionId=${encodeURIComponent(submissionId)}`);
    if (queryParts.length > 0) url += `?${queryParts.join("&")}`;

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("Fetch failed");
        return res.json();
      })
      .then((data: MatchItem[]) => {
        clientCache.setMatchList(cacheKey, data);
        setMatchList(data);
        if (data.length > 0) {
          let targetMatch = data[0];
          if (submissionId) {
            const found = data.find((m) => m.submissionAId === submissionId || m.submissionBId === submissionId);
            if (found) targetMatch = found;
          }
          setSelectedMatch(targetMatch);
        } else {
          setSelectedMatch(null);
        }
      })
      .catch(() => {
        setMatchList([]);
        setSelectedMatch(null);
      })
      .finally(() => {
        setLoadingMatches(false);
      });
  }, [teamId, submissionId]);

  // Fetch Replay Data when selectedMatch changes (with client memory cache for 0ms loads)
  useEffect(() => {
    if (!selectedMatch) return;

    if (selectedMatch.status !== "finished") {
      Promise.resolve().then(() => setReplay(null));
      return;
    }

    const cached = clientCache.getReplay(selectedMatch.id);
    if (cached) {
      Promise.resolve().then(() => setReplay(cached));
      return;
    }

    const headers: Record<string, string> = {};
    if (session?.token) headers["Authorization"] = `Bearer ${session.token}`;

    fetch(`/api/replays/${selectedMatch.id}`, { headers })
      .then((res) => {
        if (!res.ok) throw new Error("Replay fetch error");
        return res.json();
      })
      .then((data: ReplayData) => {
        clientCache.setReplay(selectedMatch.id, data);
        setReplay(data);
      })
      .catch(() => {
        setReplay(null);
      });
  }, [selectedMatch, session]);

  // Sidebar Entrance Animation
  useEffect(() => {
    if (sidebarRef.current && matchList.length > 0) {
      animate(sidebarRef.current.querySelectorAll(".history-item-anim"), {
        opacity: [0, 1],
        translateX: [-12, 0],
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delay: (_el: any, i = 0) => i * 40,
        duration: 500,
        ease: "outQuint",
      });
    }
  }, [matchList]);

  // Stop replay at full elimination (when either player has 0 planets AND 0 total ships)
  const maxStep = useMemo(() => {
    if (!replay || !replay.steps || replay.steps.length === 0) return 0;

    for (let i = 0; i < replay.steps.length; i++) {
      const stepData = replay.steps[i];
      const rawPlanets = stepData.observation?.planets || [];
      const rawFleets = stepData.observation?.fleets || [];

      let p0Planets = 0, p1Planets = 0;
      let p0TotalShips = 0, p1TotalShips = 0;

      for (const p of rawPlanets) {
        const owner = p[1];
        const ships = p[5] || 0;
        if (owner === 0) {
          p0Planets += 1;
          p0TotalShips += ships;
        } else if (owner === 1) {
          p1Planets += 1;
          p1TotalShips += ships;
        }
      }

      for (const f of rawFleets) {
        const owner = f[1];
        const ships = f[6] || 0;
        if (owner === 0) {
          p0TotalShips += ships;
        } else if (owner === 1) {
          p1TotalShips += ships;
        }
      }

      // If either player is completely eliminated (0 planets AND 0 ships/fleets anywhere)
      if (i > 0 && ((p0Planets === 0 && p0TotalShips === 0) || (p1Planets === 0 && p1TotalShips === 0))) {
        return i;
      }
    }

    return replay.steps.length - 1;
  }, [replay]);

  // Smooth, high-precision requestAnimationFrame playback loop
  useEffect(() => {
    if (!playing || !replay) return;
    const speedMap: Record<number, number> = { 0.5: 300, 1: 150, 2: 75, 4: 35 };
    const intervalMs = speedMap[speedMultiplier] || 150;

    let animId: number;
    let lastTime = performance.now();
    let accumulatedMs = 0;

    const loop = (now: number) => {
      const delta = now - lastTime;
      lastTime = now;
      accumulatedMs += delta;

      if (accumulatedMs >= intervalMs) {
        const stepsToAdvance = Math.floor(accumulatedMs / intervalMs);
        accumulatedMs %= intervalMs;
        setStep((s) => {
          const next = s + stepsToAdvance;
          if (next >= maxStep) {
            setPlaying(false);
            return maxStep;
          }
          return next;
        });
      }
      animId = requestAnimationFrame(loop);
    };

    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, [playing, speedMultiplier, replay, maxStep]);

  const copySeed = () => {
    if (!selectedMatch) return;
    navigator.clipboard.writeText(String(selectedMatch.seed));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadMatchJson = (e: React.MouseEvent, matchId: string) => {
    e.stopPropagation();

    const triggerDownload = (jsonObj: unknown) => {
      const blob = new Blob([JSON.stringify(jsonObj, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `match-${matchId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    };

    const cached = clientCache.getReplay(matchId);
    if (cached) {
      triggerDownload(cached);
      return;
    }

    const headers: Record<string, string> = {};
    if (session?.token) headers["Authorization"] = `Bearer ${session.token}`;

    fetch(`/api/replays/${matchId}`, { headers })
      .then((res) => res.json())
      .then((data) => {
        clientCache.setReplay(matchId, data);
        triggerDownload(data);
      })
      .catch(() => {});
  };

  const currentStep = replay ? replay.steps[Math.min(step, replay.steps.length - 1)] : null;

  // Compute live match telemetry statistics from currentStep
  const telemetry = useMemo(() => {
    if (!currentStep) return null;

    const rawPlanets = currentStep.observation?.planets || [];
    const rawFleets = currentStep.observation?.fleets || [];

    let p0Ships = 0, p1Ships = 0;
    let p0Planets = 0, p1Planets = 0, neutralPlanets = 0;
    let p0Prod = 0, p1Prod = 0;

    for (const p of rawPlanets) {
      const owner = p[1];
      const ships = p[5] || 0;
      const prod = p[6] || 0;

      if (owner === 0) {
        p0Ships += ships;
        p0Planets += 1;
        p0Prod += prod;
      } else if (owner === 1) {
        p1Ships += ships;
        p1Planets += 1;
        p1Prod += prod;
      } else {
        neutralPlanets += 1;
      }
    }

    let p0FleetShips = 0, p1FleetShips = 0;
    let p0FleetsCount = 0, p1FleetsCount = 0;

    for (const f of rawFleets) {
      const owner = f[1];
      const ships = f[6] || 0;
      if (owner === 0) {
        p0Ships += ships;
        p0FleetShips += ships;
        p0FleetsCount += 1;
      } else if (owner === 1) {
        p1Ships += ships;
        p1FleetShips += ships;
        p1FleetsCount += 1;
      }
    }

    const totalShips = Math.max(1, p0Ships + p1Ships);
    const p0ShipPct = Math.round((p0Ships / totalShips) * 100);
    const p1ShipPct = Math.round((p1Ships / totalShips) * 100);

    return {
      p0Ships,
      p1Ships,
      p0Planets,
      p1Planets,
      neutralPlanets,
      p0Prod,
      p1Prod,
      p0FleetShips,
      p1FleetShips,
      p0FleetsCount,
      p1FleetsCount,
      p0ShipPct,
      p1ShipPct,
    };
  }, [currentStep]);

  const returnLink = submissionId ? "/submit" : "/leaderboard";
  const returnLabel = submissionId ? "Submissions" : "Leaderboard";

  return (
    <>
      {/* MOBILE FALLBACK (Hides complex 2D canvas on small mobile screens) */}
      <div className="lg:hidden flex flex-col items-center justify-center min-h-[60vh] p-6 text-center space-y-4 max-w-md mx-auto font-mono">
        <div className="p-4 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-700">
          <Monitor className="w-8 h-8" />
        </div>
        <h2 className="text-lg font-bold text-foreground uppercase tracking-tight">
          [ DESKTOP_REQUIRED ]
        </h2>
        <p className="text-xs text-muted-foreground leading-relaxed">
          The 2D interactive space telemetry replay visualizer requires a larger screen. Please switch to a desktop or laptop computer to view match replays.
        </p>
        <Link
          href={returnLink}
          className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-5 py-2 text-xs"
        >
          Return to {returnLabel}
        </Link>
      </div>

      {/* DESKTOP REPLAY WORKSPACE (Visible on lg: and larger screens) */}
      <div className="hidden lg:flex flex-col lg:flex-row h-[calc(100vh-6.5rem)] -my-5 -mx-4 sm:-mx-6 overflow-hidden bg-background text-foreground transition-colors duration-200 border-t border-border">
      {/* LEFT SIDEBAR: GAME HISTORY / EPISODES */}
      <aside className="w-full lg:w-72 border-r border-border bg-card flex flex-col shrink-0 overflow-hidden">
        {/* Sidebar Header */}
        <div className="p-3 border-b border-border flex items-center justify-between bg-muted/30">
          <div className="flex items-center gap-2">
            <Link
              href={returnLink}
              className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              title={`Return to ${returnLabel}`}
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <h2 className="font-mono text-xs font-bold tracking-tight text-foreground uppercase truncate max-w-[180px]">
              {artifactParam ? `Episodes: ${artifactParam}` : teamNameParam ? `Team: ${teamNameParam}` : "Game History"}
            </h2>
          </div>
        </div>

        {/* Subheader Filters */}
        <div className="p-2.5 border-b border-border flex items-center justify-between text-xs font-mono bg-muted/10">
          <div>
            <span className="text-foreground font-bold uppercase text-[11px]">Match History</span>
            <div className="text-[10px] text-muted-foreground">{matchList.length} matches recorded</div>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadAll}
              disabled={downloadingZip || loadingMatches || matchList.length === 0}
              className="h-6 px-2 text-[10px] font-mono border-border hover:bg-muted gap-1"
              title="Download all replays as ZIP"
            >
              {downloadingZip ? (
                <>
                  <RotateCcw className="w-3 h-3 animate-spin" />
                  ZIP {downloadProgress}
                </>
              ) : (
                <>
                  <Download className="w-3 h-3" />
                  ZIP
                </>
              )}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-6 px-2 text-[10px] font-mono border-border hover:bg-muted gap-1"
            >
              <Filter className="w-3 h-3" />
              Filter
            </Button>
          </div>
        </div>

        {/* Match History List */}
        <div ref={sidebarRef} className="flex-1 overflow-y-auto p-2.5 space-y-2 font-mono">
          {loadingMatches ? (
            Array.from({ length: 4 }).map((_, idx) => (
              <div key={idx} className="p-3 rounded-md border border-border space-y-2">
                <div className="flex justify-between items-center">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-3 w-8" />
                </div>
                <div className="flex justify-between items-center">
                  <Skeleton className="h-3.5 w-20" />
                  <Skeleton className="h-3 w-8" />
                </div>
              </div>
            ))
          ) : matchList.length === 0 ? (
            <div className="py-12 text-center text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
              No Matches Found
            </div>
          ) : (
            matchList.map((m) => {
              const isSelected = selectedMatch?.id === m.id;
              return (
                <div
                  key={m.id}
                  onClick={() => selectMatch(m)}
                  className={`history-item-anim w-full text-left p-2.5 rounded-2xl border transition-all cursor-pointer space-y-2 ${
                    isSelected
                      ? "bg-secondary/70 border-primary/60 shadow-xs"
                      : "bg-background/60 border-border/80 hover:bg-muted/40 hover:border-border"
                  } ${m.status !== "finished" ? "opacity-60" : ""}`}
                >
                  {/* Card Header: Relative time on left, Download on right */}
                  <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground/80 px-1">
                    <span>{formatRelativeTime(m.finishedAt || m.createdAt)}</span>
                    <button
                      type="button"
                      onClick={(e) => downloadMatchJson(e, m.id)}
                      className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0 cursor-pointer"
                      title="Download match JSON data"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Card Inner Box with Team Rows & Divider */}
                  <div className="rounded-xl border border-border/70 bg-background/50 p-2.5 space-y-2 font-mono">
                    {/* Team A (Blue) */}
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2 truncate max-w-[170px]">
                        {m.teamAImage ? (
                          <img
                            src={m.teamAImage}
                            alt={m.teamA}
                            className="w-6 h-6 rounded-full object-cover shrink-0 border border-blue-500/40"
                          />
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-blue-500/15 border border-blue-500/35 flex items-center justify-center shrink-0 text-blue-600">
                            <Bot className="w-3.5 h-3.5" />
                          </div>
                        )}
                        <span className={`truncate font-semibold text-xs ${m.winner === "a" ? "text-foreground" : "text-muted-foreground"}`}>
                          {m.teamA}
                        </span>
                        {m.winner === "a" && (
                          <Trophy className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                        )}
                      </div>
                      <div className="flex items-center gap-1 font-mono text-[11px] shrink-0">
                        <span className="font-bold text-foreground">
                          {m.teamARating ? Math.round(m.teamARating) : 600}
                        </span>
                        {m.teamAChange != null && (
                          <span className={`text-[10px] font-semibold ${
                            m.teamAChange > 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : m.teamAChange < 0
                              ? "text-red-500 dark:text-red-400"
                              : "text-muted-foreground"
                          }`}>
                            ({m.teamAChange > 0 ? `+${m.teamAChange}` : m.teamAChange})
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Horizontal Inner Divider */}
                    <div className="border-t border-border/60" />

                    {/* Team B (Orange) */}
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2 truncate max-w-[170px]">
                        {m.teamBImage ? (
                          <img
                            src={m.teamBImage}
                            alt={m.teamB}
                            className="w-6 h-6 rounded-full object-cover shrink-0 border border-orange-500/40"
                          />
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-orange-500/15 border border-orange-500/35 flex items-center justify-center shrink-0 text-orange-600">
                            <Bot className="w-3.5 h-3.5" />
                          </div>
                        )}
                        <span className={`truncate font-semibold text-xs ${m.winner === "b" ? "text-foreground" : "text-muted-foreground"}`}>
                          {m.teamB}
                        </span>
                        {m.winner === "b" && (
                          <Trophy className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                        )}
                      </div>
                      <div className="flex items-center gap-1 font-mono text-[11px] shrink-0">
                        <span className="font-bold text-foreground">
                          {m.teamBRating ? Math.round(m.teamBRating) : 600}
                        </span>
                        {m.teamBChange != null && (
                          <span className={`text-[10px] font-semibold ${
                            m.teamBChange > 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : m.teamBChange < 0
                              ? "text-red-500 dark:text-red-400"
                              : "text-muted-foreground"
                          }`}>
                            ({m.teamBChange > 0 ? `+${m.teamBChange}` : m.teamBChange})
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* RIGHT MAIN GAME AREA */}
      <main className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden bg-background">
        {/* Top Match Score Bar & Telemetry Toggles */}
        {selectedMatch && (
          <div className="p-2.5 px-4 border-b border-border bg-card flex flex-wrap items-center justify-between gap-3 text-xs font-mono shrink-0">
            {/* Teams & Winner Badges with Rating Change (+15 / -15) */}
            {(() => {
              const winner = selectedMatch.winner;
              const isDraw = winner === "draw" || !winner;
              const isWinA = winner === "a";
              const isWinB = winner === "b";

              const changeA = selectedMatch.teamAChange ?? (isDraw ? 0 : isWinA ? 15 : -15);
              const changeB = selectedMatch.teamBChange ?? (isDraw ? 0 : isWinB ? 15 : -15);

              const formatDiff = (val: number) => (val > 0 ? `(+${val})` : `(${val})`);

              return (
                <div className="flex items-center gap-3">
                  <div
                    className={`px-2.5 py-1 rounded border text-[11px] font-bold flex items-center gap-1.5 ${
                      isDraw
                        ? "bg-muted text-muted-foreground border-border"
                        : isWinA
                          ? "bg-blue-500/15 text-blue-700 border-blue-500/30"
                          : "bg-destructive/15 text-destructive border-destructive/30"
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full bg-blue-600 shrink-0" />
                    [{isDraw ? "Draw" : isWinA ? "Win" : "Loss"}] {selectedMatch.teamA} {formatDiff(changeA)}
                  </div>

                  <span className="text-muted-foreground font-bold">vs</span>

                  <div
                    className={`px-2.5 py-1 rounded border text-[11px] font-bold flex items-center gap-1.5 ${
                      isDraw
                        ? "bg-muted text-muted-foreground border-border"
                        : isWinB
                          ? "bg-orange-500/15 text-orange-700 border-orange-500/30"
                          : "bg-destructive/15 text-destructive border-destructive/30"
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full bg-orange-600 shrink-0" />
                    [{isDraw ? "Draw" : isWinB ? "Win" : "Loss"}] {selectedMatch.teamB} {formatDiff(changeB)}
                  </div>
                </div>
              );
            })()}

            {/* Telemetry Display Toggles */}
            <div className="flex items-center gap-1.5">
              <Button
                variant={showFleetNum ? "default" : "outline"}
                size="sm"
                onClick={() => setShowFleetNum(!showFleetNum)}
                className="h-6 px-2 text-[10px] font-mono border-border"
              >
                Fleet #
              </Button>
              <Button
                variant={showProduction ? "default" : "outline"}
                size="sm"
                onClick={() => setShowProduction(!showProduction)}
                className="h-6 px-2 text-[10px] font-mono border-border"
              >
                Production
              </Button>
              <Button
                variant={showTrajectories ? "default" : "outline"}
                size="sm"
                onClick={() => setShowTrajectories(!showTrajectories)}
                className="h-6 px-2 text-[10px] font-mono border-border"
              >
                Trajectories
              </Button>
              <div className="flex items-center border border-border rounded-md overflow-hidden p-0.5 bg-muted/40">
                {(["all", "small", "medium", "large"] as const).map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setFleetSizeFilter(filter)}
                    type="button"
                    className={`px-1.5 py-0.5 text-[10px] font-mono uppercase rounded capitalize transition-all cursor-pointer ${
                      fleetSizeFilter === filter
                        ? "bg-primary text-primary-foreground font-bold shadow-xs"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {filter}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Center Space Canvas Visualizer + Side Telemetry Cards (Fills Wasted Space) */}
        <div className="flex-1 min-h-0 flex items-center justify-center gap-4 p-3 bg-background relative overflow-hidden">
          {/* Left Telemetry Panel (Player 0 / Blue) */}
          {telemetry && selectedMatch && (
            <div className="hidden xl:flex flex-col gap-3 w-56 shrink-0 font-mono text-xs p-3.5 bg-card border border-border rounded-lg shadow-xs">
              <div className="flex items-center gap-1.5 pb-2 border-b border-border">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-600 shrink-0" />
                <span className="font-bold text-foreground truncate">{selectedMatch.teamA}</span>
              </div>

              <div className="space-y-1">
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Armada Share</span>
                  <span className="font-bold text-blue-600">{telemetry.p0ShipPct}%</span>
                </div>
                <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-blue-600 transition-all duration-300" style={{ width: `${telemetry.p0ShipPct}%` }} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div className="bg-muted/50 p-2 rounded border border-border/60">
                  <div className="text-[10px] text-muted-foreground uppercase">Total Ships</div>
                  <div className="text-sm font-bold text-foreground">{telemetry.p0Ships}</div>
                </div>
                <div className="bg-muted/50 p-2 rounded border border-border/60">
                  <div className="text-[10px] text-muted-foreground uppercase">Income</div>
                  <div className="text-sm font-bold text-emerald-700">+{telemetry.p0Prod}/t</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="bg-muted/50 p-2 rounded border border-border/60">
                  <div className="text-[10px] text-muted-foreground uppercase">Planets</div>
                  <div className="text-sm font-bold text-foreground">{telemetry.p0Planets}</div>
                </div>
                <div className="bg-muted/50 p-2 rounded border border-border/60">
                  <div className="text-[10px] text-muted-foreground uppercase">In Transit</div>
                  <div className="text-sm font-bold text-blue-600">{telemetry.p0FleetShips} <span className="text-[10px] font-normal">({telemetry.p0FleetsCount})</span></div>
                </div>
              </div>
            </div>
          )}

          {/* Main Square Board Canvas */}
          <div ref={canvasContainerRef} className="flex-1 flex items-center justify-center min-w-0 h-full relative">
            {currentStep ? (
              <ReplayRenderer
                step={currentStep}
                width={canvasDim}
                height={canvasDim}
                showFleetNum={showFleetNum}
                showProduction={showProduction}
                showTrajectories={showTrajectories}
                fleetSizeFilter={fleetSizeFilter}
              />
            ) : loadingMatches ? (
              <div className="flex flex-col items-center justify-center space-y-3 font-mono">
                <div className="w-8 h-8 border border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-xs text-muted-foreground uppercase tracking-widest animate-pulse">
                  LOADING MATCH HISTORY...
                </span>
              </div>
            ) : selectedMatch && selectedMatch.status !== "finished" ? (
              <div className="flex flex-col items-center justify-center space-y-4 max-w-sm mx-auto text-center font-mono p-6 bg-card border border-border rounded-lg shadow-xs">
                <div className="p-3 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-600 animate-pulse">
                  <Monitor className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-amber-600 uppercase tracking-wide">
                    [ MATCH IN PROGRESS ]
                  </h3>
                  <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                    This episode is currently being simulated by the worker node.
                    The replay will be available as soon as it finishes.
                  </p>
                </div>
              </div>
            ) : selectedMatch ? (
              <div className="flex flex-col items-center justify-center space-y-3 font-mono">
                <div className="w-8 h-8 border border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-xs text-muted-foreground uppercase tracking-widest animate-pulse">
                  INITIALIZING SPACE TELEMETRY...
                </span>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center space-y-4 max-w-sm mx-auto text-center font-mono p-6 bg-card border border-border rounded-lg shadow-xs">
                <div className="p-3 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-600">
                  <Trophy className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">
                    [ NO_EPISODES_AVAILABLE ]
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                    {artifactParam
                      ? `No recorded match episodes found for ${artifactParam} yet.`
                      : teamNameParam
                        ? `No recorded match episodes found for ${teamNameParam} yet.`
                        : "No recorded match episodes found on the ladder yet."}
                  </p>
                </div>
                <Link
                  href={returnLink}
                  className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-4 py-2 text-xs inline-flex items-center gap-1.5"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>Return to {returnLabel}</span>
                </Link>
              </div>
            )}

            {/* Elden Ring Inspired Game Over Banner Overlay */}
            {selectedMatch && step >= maxStep && maxStep > 0 && (() => {
              const winner = selectedMatch.winner;
              const isDraw = winner === "draw" || !winner;
              const isWinA = winner === "a";

              const winnerName = isDraw ? null : isWinA ? selectedMatch.teamA : selectedMatch.teamB;
              const winnerChange = isDraw ? 0 : isWinA ? (selectedMatch.teamAChange ?? 15) : (selectedMatch.teamBChange ?? 15);
              const loserName = isDraw ? null : isWinA ? selectedMatch.teamB : selectedMatch.teamA;
              const loserChange = isDraw ? 0 : isWinA ? (selectedMatch.teamBChange ?? -15) : (selectedMatch.teamAChange ?? -15);

              const winnerScore = isDraw ? 0 : isWinA ? (selectedMatch.scores?.[0] ?? 0) : (selectedMatch.scores?.[1] ?? 0);
              const loserScore = isDraw ? 0 : isWinA ? (selectedMatch.scores?.[1] ?? 0) : (selectedMatch.scores?.[0] ?? 0);

              const winChangeStr = winnerChange > 0 ? `+${winnerChange}` : `${winnerChange}`;
              const loseChangeStr = loserChange > 0 ? `+${loserChange}` : `${loserChange}`;

              return (
                <div className="absolute inset-x-0 z-30 pointer-events-none flex items-center justify-center">
                  <div className="w-full bg-stone-950/95 py-6 sm:py-8 border-y-2 border-amber-600/80 flex flex-col items-center justify-center text-center shadow-[0_10px_40px_rgba(0,0,0,0.9)] transition-all duration-700 animate-in fade-in zoom-in-95">
                    <h2 className="font-serif text-4xl sm:text-6xl font-black uppercase tracking-[0.4em] text-red-500 drop-shadow-[0_2px_10px_rgba(0,0,0,1)] select-none">
                      GAME OVER
                    </h2>
                    {isDraw ? (
                      <div className="font-serif tracking-widest text-sm sm:text-base text-amber-300 font-semibold mt-2.5 drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]">
                        Match ended in a draw!
                      </div>
                    ) : (
                      <div className="font-serif tracking-widest text-sm sm:text-base text-amber-300 font-semibold mt-2.5 drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]">
                        [1st] {winnerName} ({winChangeStr}) wins!
                      </div>
                    )}
                    <div className="font-mono text-xs sm:text-sm text-stone-200 font-medium mt-1.5 tracking-wider drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]">
                      {isDraw ? (
                        `[1st] ${selectedMatch.teamA} (0) — [1st] ${selectedMatch.teamB} (0)`
                      ) : (
                        `[1st] ${winnerName} (${winChangeStr}): ${winnerScore} — [2nd] ${loserName} (${loseChangeStr}): ${loserScore}`
                      )}
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>

          {/* Right Telemetry Panel (Player 1 / Orange) */}
          {telemetry && selectedMatch && (
            <div className="hidden xl:flex flex-col gap-3 w-56 shrink-0 font-mono text-xs p-3.5 bg-card border border-border rounded-lg shadow-xs">
              <div className="flex items-center gap-1.5 pb-2 border-b border-border">
                <span className="w-2.5 h-2.5 rounded-full bg-orange-600 shrink-0" />
                <span className="font-bold text-foreground truncate">{selectedMatch.teamB}</span>
              </div>

              <div className="space-y-1">
                <div className="flex justify-between text-[11px]">
                  <span className="text-muted-foreground">Armada Share</span>
                  <span className="font-bold text-orange-600">{telemetry.p1ShipPct}%</span>
                </div>
                <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-orange-600 transition-all duration-300" style={{ width: `${telemetry.p1ShipPct}%` }} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div className="bg-muted/50 p-2 rounded border border-border/60">
                  <div className="text-[10px] text-muted-foreground uppercase">Total Ships</div>
                  <div className="text-sm font-bold text-foreground">{telemetry.p1Ships}</div>
                </div>
                <div className="bg-muted/50 p-2 rounded border border-border/60">
                  <div className="text-[10px] text-muted-foreground uppercase">Income</div>
                  <div className="text-sm font-bold text-emerald-700">+{telemetry.p1Prod}/t</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="bg-muted/50 p-2 rounded border border-border/60">
                  <div className="text-[10px] text-muted-foreground uppercase">Planets</div>
                  <div className="text-sm font-bold text-foreground">{telemetry.p1Planets}</div>
                </div>
                <div className="bg-muted/50 p-2 rounded border border-border/60">
                  <div className="text-[10px] text-muted-foreground uppercase">In Transit</div>
                  <div className="text-sm font-bold text-orange-600">{telemetry.p1FleetShips} <span className="text-[10px] font-normal">({telemetry.p1FleetsCount})</span></div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Bottom Playback Controls Bar */}
        {selectedMatch && (
          <div className="p-2.5 px-4 border-t border-border bg-card flex flex-wrap items-center gap-4 text-xs font-mono shrink-0">
            {/* Copy Seed */}
            <button
              onClick={copySeed}
              type="button"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-muted/60 border border-border hover:bg-muted text-foreground transition-colors cursor-pointer text-[11px]"
              title="Click to copy match seed"
            >
              <span>Seed: {selectedMatch.seed}</span>
              {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-600" />
              ) : (
                <Copy className="w-3.5 h-3.5 text-muted-foreground" />
              )}
            </button>

            {/* Playback Step Control Buttons */}
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon-sm"
                onClick={() => setStep(0)}
                disabled={step === 0}
                title="Restart Replay"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </Button>
              <Button
                variant="outline"
                size="icon-sm"
                onClick={() => setStep((s) => Math.max(0, s - 1))}
                disabled={step === 0}
                title="Step Back"
              >
                <SkipBack className="w-3.5 h-3.5" />
              </Button>
              <Button
                variant="default"
                size="icon-sm"
                onClick={() => setPlaying(!playing)}
                title={playing ? "Pause" : "Play"}
              >
                {playing ? (
                  <Pause className="w-3.5 h-3.5" />
                ) : (
                  <Play className="w-3.5 h-3.5 ml-0.5" />
                )}
              </Button>
              <Button
                variant="outline"
                size="icon-sm"
                onClick={() => setStep((s) => Math.min(maxStep, s + 1))}
                disabled={step === maxStep}
                title="Step Forward"
              >
                <SkipForward className="w-3.5 h-3.5" />
              </Button>
            </div>

            {/* Scrubber Range Slider */}
            <div className="flex-1 flex items-center gap-3 min-w-[200px]">
              <input
                type="range"
                min={0}
                max={maxStep}
                value={step}
                onChange={(e) => setStep(Number(e.target.value))}
                className="flex-1 accent-primary h-1.5 rounded-lg bg-muted border-none cursor-pointer"
              />
              <span className="text-[11px] text-muted-foreground w-16 text-right font-bold">
                {step} / {maxStep}
              </span>
            </div>

            {/* Speed Multiplier Select (0.5x, 1x, 2x, 4x) */}
            <div className="flex items-center gap-1 border border-border rounded-md p-0.5 bg-muted/40">
              {([0.5, 1, 2, 4] as const).map((spd) => (
                <button
                  key={spd}
                  onClick={() => setSpeedMultiplier(spd)}
                  type="button"
                  className={`px-2 py-0.5 text-[10px] font-mono rounded transition-all cursor-pointer ${
                    speedMultiplier === spd
                      ? "bg-primary text-primary-foreground font-bold"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {spd}x
                </button>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  </>
);
}

export default function GameHistoryPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-3 font-mono">
        <div className="w-8 h-8 border border-primary border-t-transparent rounded-full animate-spin" />
        <span className="text-xs text-muted-foreground uppercase tracking-widest animate-pulse">
          LOADING MATCH REPLAYS...
        </span>
      </div>
    }>
      <GameHistoryContent />
    </Suspense>
  );
}

