"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import Link from "next/link";
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
  SlidersHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReplayRenderer } from "@/components/replay/ReplayRenderer";
import { useSession } from "@/lib/auth-client";
import { clientCache } from "@/lib/client-cache";
import { animate } from "animejs";
import { formatRelativeTime, useTick } from "@/lib/time";

interface MatchItem {
  id: string;
  seed: number;
  kind: string;
  teamA: string;
  teamB: string;
  teamARating: number;
  teamBRating: number;
  winner: "a" | "b" | "draw";
  winnerName: string | null;
  scores: number[];
  createdAt: string;
  finishedAt: string | null;
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

export default function MatchReplayPage({
  params,
}: {
  params: Promise<{ matchId: string }>;
}) {
  const { data: session } = useSession();
  const [matchIdParam, setMatchIdParam] = useState<string>("");
  const [matchList, setMatchList] = useState<MatchItem[]>([]);
  const [selectedMatch, setSelectedMatch] = useState<MatchItem | null>(null);
  const [replay, setReplay] = useState<ReplayData | null>(null);

  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speedMultiplier, setSpeedMultiplier] = useState<1 | 2 | 4>(1);
  const [copied, setCopied] = useState(false);

  // Telemetry Controls
  const [showFleetNum, setShowFleetNum] = useState(true);
  const [showProduction, setShowProduction] = useState(true);
  const [showTrajectories, setShowTrajectories] = useState(false);
  const [fleetSizeFilter, setFleetSizeFilter] = useState<"all" | "small" | "medium" | "large">("all");

  const [canvasDim, setCanvasDim] = useState(540);
  const canvasContainerRef = useRef<HTMLDivElement>(null);

  // Re-render every second to keep relative time labels fresh
  useTick(1000);

  const sidebarRef = useRef<HTMLDivElement>(null);

  // Responsive canvas sizing via ResizeObserver
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

  useEffect(() => {
    params.then((p) => {
      setMatchIdParam(p.matchId);
    });
  }, [params]);

  const selectMatch = (m: MatchItem) => {
    setSelectedMatch(m);
    setReplay(null);
    setStep(0);
    setPlaying(false);
  };

  // Fetch Game History Match List (with client cache for 15s)
  useEffect(() => {
    const cacheKey = "all";
    const cached = clientCache.getMatchList(cacheKey);
    if (cached && cached.length > 0) {
      Promise.resolve().then(() => {
        setMatchList(cached);
        const found = cached.find((m) => m.id === matchIdParam);
        if (found) {
          setSelectedMatch(found);
        } else if (cached.length > 0) {
          setSelectedMatch(cached[0]);
        }
      });
      return;
    }

    fetch("/api/replays")
      .then((res) => {
        if (!res.ok) throw new Error("Fetch failed");
        return res.json();
      })
      .then((data: MatchItem[]) => {
        clientCache.setMatchList(cacheKey, data);
        setMatchList(data);
        const found = data.find((m) => m.id === matchIdParam);
        if (found) {
          setSelectedMatch(found);
        } else if (data.length > 0) {
          setSelectedMatch(data[0]);
        }
      })
      .catch(() => {
        setMatchList([]);
      });
  }, [matchIdParam]);

  // Fetch Replay Data when selectedMatch changes (with client memory cache for 0ms loads)
  useEffect(() => {
    if (!selectedMatch) return;

    const cached = clientCache.getReplay(selectedMatch.id);
    if (cached) {
      Promise.resolve().then(() => {
        setReplay(cached);
        setStep(0);
        setPlaying(false);
      });
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
        setStep(0);
        setPlaying(false);
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
    const intervalMs = Math.max(20, 100 / speedMultiplier);

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

  const currentStep = replay ? replay.steps[Math.min(step, replay.steps.length - 1)] : null;

  return (
    <div className="replay-workspace flex flex-col lg:flex-row h-[calc(100vh-6rem)] -my-7 -mx-5 sm:-mx-8 overflow-hidden text-foreground transition-colors duration-200">
      {/* LEFT SIDEBAR: GAME HISTORY */}
      <aside className="w-full lg:w-80 border-r border-border bg-card flex flex-col shrink-0 overflow-hidden">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-border flex items-center justify-between bg-muted/30">
          <div className="flex items-center gap-2">
            <Link
              href="/leaderboard"
              className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              title="Return to Leaderboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <h2 className="font-mono text-sm font-bold tracking-tight text-foreground uppercase">
              Match archive
            </h2>
          </div>
        </div>

        {/* Subheader Filters */}
        <div className="p-3 border-b border-border flex items-center justify-between text-xs font-mono bg-muted/10">
          <div>
            <span className="text-foreground font-bold uppercase">Recent duels</span>
            <div className="text-[10px] text-muted-foreground">{matchList.length} matches</div>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-[10px] font-mono border-border hover:bg-muted gap-1"
            >
              <Filter className="w-3 h-3" />
              Filters
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 text-muted-foreground hover:text-foreground"
              title="Grid options"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>

        {/* Match History List */}
        <div ref={sidebarRef} className="flex-1 overflow-y-auto p-3 space-y-3 font-mono">
            {matchList.length > 0 && (
            <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold px-1">
              {matchList.length} matches recorded
            </div>
          )}

          {matchList.map((m) => {
            const isSelected = selectedMatch?.id === m.id;
            return (
              <button
                key={m.id}
                onClick={() => selectMatch(m)}
                type="button"
                className={`history-item-anim w-full text-left p-3 rounded-lg border transition-all cursor-pointer ${
                  isSelected
                    ? "bg-secondary border-primary/60 shadow-xs"
                    : "bg-background/60 border-border/80 hover:bg-muted/50 hover:border-border"
                }`}
              >
                {/* Team A */}
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <div className="flex items-center gap-1.5 truncate max-w-[170px]">
                    <span className="w-1.5 h-1.5 rounded-full bg-sky-500 shrink-0" />
                    <span className={`truncate font-semibold ${m.winner === "a" ? "text-foreground" : "text-muted-foreground"}`}>
                      {m.teamA}
                    </span>
                    {m.winner === "a" && (
                      <Trophy className="w-3 h-3 text-amber-500 shrink-0" />
                    )}
                  </div>
                </div>

                {/* Team B */}
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5 truncate max-w-[170px]">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                    <span className={`truncate font-semibold ${m.winner === "b" ? "text-foreground" : "text-muted-foreground"}`}>
                      {m.teamB}
                    </span>
                    {m.winner === "b" && (
                      <Trophy className="w-3 h-3 text-amber-500 shrink-0" />
                    )}
                  </div>
                </div>

                {/* Relative time (computed client-side for live updates) */}
                <div className="text-[10px] text-muted-foreground/70 mt-1 font-mono">
                  {formatRelativeTime(m.finishedAt || m.createdAt)}
                </div>
              </button>
            );
          })}
        </div>
      </aside>

      {/* RIGHT MAIN GAME AREA */}
      <main className="flex-1 flex flex-col overflow-hidden bg-background">
        <div className="px-5 pt-4 pb-1 flex items-center justify-between font-mono">
          <span className="nw-kicker">Match theatre / live telemetry</span>
          <span className="text-[10px] text-muted-foreground">FIELD 100 × 100</span>
        </div>
        {/* Top Match Score Bar & Telemetry Toggles */}
        {selectedMatch && (
          <div className="p-3 border-b border-border bg-card flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
            {/* Teams & Winner Badges */}
            <div className="flex items-center gap-3">
              <div className={`px-2.5 py-1 rounded border text-[11px] font-bold ${
                selectedMatch.winner === "draw"
                  ? "bg-muted text-muted-foreground border-border"
                  : selectedMatch.winner === "a"
                  ? "bg-sky-500/15 text-sky-500 border-sky-500/30"
                  : "bg-destructive/15 text-destructive border-destructive/30"
              }`}>
                [{selectedMatch.winner === "a" ? "Win" : selectedMatch.winner === "draw" ? "Draw" : "Loss"}] {selectedMatch.teamA} ({selectedMatch.scores[0] ?? 25})
              </div>

              <span className="text-muted-foreground font-bold">vs</span>

              <div className={`px-2.5 py-1 rounded border text-[11px] font-bold ${
                selectedMatch.winner === "draw"
                  ? "bg-muted text-muted-foreground border-border"
                  : selectedMatch.winner === "b"
                  ? "bg-amber-500/15 text-amber-500 border-amber-500/30"
                  : "bg-destructive/15 text-destructive border-destructive/30"
              }`}>
                [{selectedMatch.winner === "b" ? "Win" : selectedMatch.winner === "draw" ? "Draw" : "Loss"}] {selectedMatch.teamB} ({selectedMatch.scores[1] ?? 25})
              </div>
            </div>

            {/* Telemetry Display Toggles */}
            <div className="flex items-center gap-1.5">
              <Button
                variant={showFleetNum ? "default" : "outline"}
                size="sm"
                onClick={() => setShowFleetNum(!showFleetNum)}
                className="h-7 px-2.5 text-[10px] font-mono border-border"
              >
                Fleet #
              </Button>
              <Button
                variant={showProduction ? "default" : "outline"}
                size="sm"
                onClick={() => setShowProduction(!showProduction)}
                className="h-7 px-2.5 text-[10px] font-mono border-border"
              >
                Production
              </Button>
              <Button
                variant={showTrajectories ? "default" : "outline"}
                size="sm"
                onClick={() => setShowTrajectories(!showTrajectories)}
                className="h-7 px-2.5 text-[10px] font-mono border-border"
              >
                Trajectories
              </Button>
              <div className="flex items-center border border-border rounded-md overflow-hidden p-0.5 bg-muted/40">
                {(["all", "small", "medium", "large"] as const).map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setFleetSizeFilter(filter)}
                    type="button"
                    className={`px-2 py-0.5 text-[10px] font-mono uppercase rounded capitalize transition-all cursor-pointer ${
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

        {/* Center Space Canvas Visualizer */}
        <div ref={canvasContainerRef} className="flex-1 flex items-center justify-center p-5 sm:p-8 bg-background min-w-0 h-full">
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
          ) : (
            <div className="flex flex-col items-center justify-center space-y-3 font-mono">
              <div className="w-8 h-8 border border-primary border-t-transparent rounded-full animate-spin" />
              <span className="text-xs text-muted-foreground uppercase tracking-widest animate-pulse">
                INITIALIZING SPACE TELEMETRY...
              </span>
            </div>
          )}
        </div>

        {/* Bottom Playback Controls Bar */}
        {selectedMatch && (
          <div className="replay-dock p-4 flex flex-wrap items-center gap-4 text-xs font-mono">
            {/* Copy Seed */}
            <button
              onClick={copySeed}
              type="button"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-muted/60 border border-border hover:bg-muted text-foreground transition-colors cursor-pointer text-[11px]"
              title="Click to copy match seed"
            >
              <span>Seed: {selectedMatch.seed}</span>
              {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-500" />
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

            {/* Speed Multiplier Select */}
            <div className="flex items-center gap-1 border border-border rounded-md p-0.5 bg-muted/40">
              {([1, 2, 4] as const).map((spd) => (
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
  );
}
