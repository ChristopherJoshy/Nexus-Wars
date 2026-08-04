"use client";

import { useRef, useEffect } from "react";

const BOARD_SIZE = 100;
const CENTER = BOARD_SIZE / 2;
const SUN_RADIUS = 10.0; // Must match engine constant

// Player Color System: 0 = Vibrant Blue, 1 = Vibrant Orange, -1 = Neutral Slate
const PLAYER_COLORS = {
  0: {
    main: "#2563eb",
    stroke: "#1d4ed8",
    bg: "#dbeafe",
    glow: "rgba(37, 99, 235, 0.25)",
    text: "#1e40af",
  },
  1: {
    main: "#ea580c",
    stroke: "#c2410c",
    bg: "#ffedd5",
    glow: "rgba(234, 88, 12, 0.25)",
    text: "#9a3412",
  },
  [-1]: {
    main: "#64748b",
    stroke: "#475569",
    bg: "#f1f5f9",
    glow: "rgba(100, 116, 139, 0.15)",
    text: "#334155",
  },
};

interface Planet {
  id: number;
  owner: number;
  x: number;
  y: number;
  radius: number;
  ships: number;
  production: number;
  energy: number;
  energyCap: number;
  energyRegen: number;
}

interface Fleet {
  id: number;
  owner: number;
  x: number;
  y: number;
  angle: number;
  from_planet_id: number;
  ships: number;
  launchedStep: number;
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

interface ReplayRendererProps {
  step: StepData;
  width?: number;
  height?: number;
  showFleetNum?: boolean;
  showProduction?: boolean;
  showTrajectories?: boolean;
  fleetSizeFilter?: "all" | "small" | "medium" | "large";
}

function parsePlanets(raw: number[][]): Planet[] {
  return raw.map((p) => ({
    id: p[0] ?? 0,
    owner: p[1] ?? -1,
    x: p[2] ?? 0,
    y: p[3] ?? 0,
    radius: p[4] ?? 2,
    ships: p[5] ?? 0,
    production: p[6] ?? 0,
    energy: p[7] ?? 100,
    energyCap: p[8] ?? 100,
    energyRegen: p[9] ?? 5,
  }));
}

function parseFleets(raw: number[][]): Fleet[] {
  return raw.map((f) => ({
    id: f[0] ?? 0,
    owner: f[1] ?? -1,
    x: f[2] ?? 0,
    y: f[3] ?? 0,
    angle: f[4] ?? 0,
    from_planet_id: f[5] ?? -1,
    ships: f[6] ?? 0,
    launchedStep: f[7] ?? 0,
  }));
}

export function ReplayRenderer({
  step,
  width = 580,
  height = 580,
  showFleetNum = true,
  showProduction = true,
  showTrajectories = false,
  fleetSizeFilter = "all",
}: ReplayRendererProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Support High-DPI displays (Retina, 4K) without re-allocating canvas buffer every frame
    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    const targetW = Math.floor(width * dpr);
    const targetH = Math.floor(height * dpr);
    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Calculate padding margin so edge planets and text labels never clip
    const padding = Math.max(42, Math.round(width * 0.075));
    const drawWidth = width - padding * 2;
    const drawHeight = height - padding * 2;
    const scale = drawWidth / BOARD_SIZE;

    const toScreenX = (x: number) => padding + x * scale;
    const toScreenY = (y: number) => padding + y * scale;

    ctx.clearRect(0, 0, width, height);

    // Warm Cream Paper Background
    ctx.fillStyle = "#faf8f4";
    ctx.fillRect(0, 0, width, height);

    // Fine Paper Grid Lines
    ctx.strokeStyle = "#e8e1d5";
    ctx.lineWidth = 0.6;
    ctx.beginPath();
    for (let i = 0; i <= BOARD_SIZE; i += 10) {
      const gx = toScreenX(i);
      const gy = toScreenY(i);
      ctx.moveTo(gx, padding);
      ctx.lineTo(gx, height - padding);
      ctx.moveTo(padding, gy);
      ctx.lineTo(width - padding, gy);
    }
    ctx.stroke();

    // Outer Board Boundary Line
    ctx.strokeStyle = "#d4c9b8";
    ctx.lineWidth = 1;
    ctx.strokeRect(padding, padding, drawWidth, drawHeight);

    const planets = parsePlanets(step.observation.planets);
    let fleets = parseFleets(step.observation.fleets);

    // Filter fleets by size if requested
    if (fleetSizeFilter === "small") {
      fleets = fleets.filter((f) => f.ships <= 10);
    } else if (fleetSizeFilter === "medium") {
      fleets = fleets.filter((f) => f.ships > 10 && f.ships <= 30);
    } else if (fleetSizeFilter === "large") {
      fleets = fleets.filter((f) => f.ships > 30);
    }

    const planetsMap = new Map<number, Planet>();
    planets.forEach((p) => planetsMap.set(p.id, p));

    // Central Sun
    const sunX = toScreenX(CENTER);
    const sunY = toScreenY(CENTER);
    const sunR = SUN_RADIUS * scale;

    // Sun Solar Corona / Aura
    ctx.beginPath();
    ctx.arc(sunX, sunY, sunR * 2.4, 0, Math.PI * 2);
    const auraGrad = ctx.createRadialGradient(sunX, sunY, sunR * 0.4, sunX, sunY, sunR * 2.4);
    auraGrad.addColorStop(0, "rgba(217, 119, 6, 0.28)");
    auraGrad.addColorStop(0.5, "rgba(217, 119, 6, 0.08)");
    auraGrad.addColorStop(1, "rgba(217, 119, 6, 0)");
    ctx.fillStyle = auraGrad;
    ctx.fill();

    // Sun Body Gradient
    ctx.beginPath();
    ctx.arc(sunX, sunY, sunR, 0, Math.PI * 2);
    const sunGrad = ctx.createRadialGradient(sunX - sunR * 0.25, sunY - sunR * 0.25, 0, sunX, sunY, sunR);
    sunGrad.addColorStop(0, "#fde68a");
    sunGrad.addColorStop(0.5, "#d97706");
    sunGrad.addColorStop(1, "#b45309");
    ctx.fillStyle = sunGrad;
    ctx.fill();
    ctx.strokeStyle = "#92400e";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Optional: Fleet Trajectory Dashed Lines (Only rendered when showTrajectories is true)
    if (showTrajectories && fleets.length > 0) {
      ctx.save();
      ctx.setLineDash([3, 4]);
      ctx.globalAlpha = 0.35;
      ctx.lineWidth = 1.0;

      // Group trajectory lines by player owner color to batch draw calls
      const fleetsByOwner = new Map<number, Fleet[]>();
      for (const f of fleets) {
        const owner = f.owner;
        let list = fleetsByOwner.get(owner);
        if (!list) {
          list = [];
          fleetsByOwner.set(owner, list);
        }
        list.push(f);
      }

      for (const [owner, ownerFleets] of fleetsByOwner.entries()) {
        const pColors = PLAYER_COLORS[owner as keyof typeof PLAYER_COLORS] || PLAYER_COLORS[-1];
        ctx.strokeStyle = pColors.main;
        ctx.beginPath();

        for (const f of ownerFleets) {
          const originPlanet = planetsMap.get(f.from_planet_id);
          if (originPlanet) {
            const fx = toScreenX(f.x);
            const fy = toScreenY(f.y);
            const ox = toScreenX(originPlanet.x);
            const oy = toScreenY(originPlanet.y);
            ctx.moveTo(ox, oy);
            ctx.lineTo(fx, fy);
          }
        }
        ctx.stroke();
      }
      ctx.restore();
    }

    // Render Planet Nodes
    for (const p of planets) {
      const px = toScreenX(p.x);
      const py = toScreenY(p.y);

      // Use true game-space radius scaled to canvas — matches engine exactly
      const rawR = typeof p.radius === "number" && p.radius > 0 ? p.radius : 2.0;
      const pr = Math.max(8, rawR * scale);

      const pColors = PLAYER_COLORS[p.owner as keyof typeof PLAYER_COLORS] || PLAYER_COLORS[-1];

      // Planet Glow Aura for active player planets
      if (p.owner !== -1) {
        ctx.beginPath();
        ctx.arc(px, py, pr + 5, 0, Math.PI * 2);
        ctx.fillStyle = pColors.glow;
        ctx.fill();
      }

      // Planet Body Circle
      ctx.beginPath();
      ctx.arc(px, py, pr, 0, Math.PI * 2);
      ctx.fillStyle = pColors.main;
      ctx.fill();
      ctx.strokeStyle = pColors.stroke;
      ctx.lineWidth = 1.8;
      ctx.stroke();

      // Planet Ship Count Label inside node
      ctx.fillStyle = "#ffffff";
      ctx.font = `bold ${Math.max(9, Math.round(pr * 0.75))}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(Math.floor(p.ships)), px, py);

      // Planet Production Badge above node (+P)
      if (showProduction && p.production > 0) {
        const prodText = `+${p.production}`;
        const fontSize = Math.max(8, Math.round(drawWidth * 0.016));
        ctx.font = `bold ${fontSize}px monospace`;
        ctx.fillStyle = "#15803d";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(prodText, px, py - pr - 2);
      }
    }

    // Render Fleets — proper chevrons scaled by ship count, matching reference renderer
    for (const f of fleets) {
      const fx = toScreenX(f.x);
      const fy = toScreenY(f.y);
      const pColors = PLAYER_COLORS[f.owner as keyof typeof PLAYER_COLORS] || PLAYER_COLORS[-1];
      const angle = f.angle || 0;

      // Scale chevron size by ship count: log scale (same as reference renderer)
      const sz = Math.max(5, (0.5 + (2.5 * Math.log(Math.max(1, f.ships))) / Math.log(1000)) * scale);

      // Draw chevron using save/translate/rotate for correct orientation
      ctx.save();
      ctx.translate(fx, fy);
      ctx.rotate(angle);

      ctx.fillStyle = pColors.main;
      ctx.strokeStyle = pColors.stroke;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(sz, 0);            // tip (pointing in direction of travel)
      ctx.lineTo(-sz, -sz * 0.7);  // top wing
      ctx.lineTo(-sz * 0.3, 0);    // inner notch
      ctx.lineTo(-sz, sz * 0.7);   // bottom wing
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Player 1 gets a center stripe for colorblind accessibility
      if (f.owner === 1) {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.55)";
        ctx.lineWidth = sz * 0.15;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(sz * 0.8, 0);
        ctx.lineTo(-sz * 0.2, 0);
        ctx.stroke();
      }

      ctx.restore();

      // Render Ship Count Badge on Fleet
      if (showFleetNum) {
        const shipStr = String(Math.floor(f.ships));
        const fontSize = Math.max(8, Math.round(drawWidth * 0.015));
        ctx.font = `bold ${fontSize}px monospace`;
        const textWidth = ctx.measureText(shipStr).width;

        // Smart label offset: above fleet if in bottom half, below if in top half
        const inBottomHalf = f.y >= 50;
        const badgeX = fx;
        const badgeY = inBottomHalf ? fy - sz - 3 : fy + sz + fontSize + 3;
        const padX = 3;
        const padY = 1.5;

        // Badge Background Pill in Owner Tinted Background
        ctx.fillStyle = pColors.bg;
        ctx.strokeStyle = pColors.stroke;
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.roundRect(
          badgeX - textWidth / 2 - padX,
          badgeY - fontSize - padY,
          textWidth + padX * 2,
          fontSize + padY * 2,
          3
        );
        ctx.fill();
        ctx.stroke();

        // Ship Count Text in Owner Dark Color
        ctx.fillStyle = pColors.text;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(shipStr, badgeX, badgeY);
      }
    }

    // Step Counter Watermark (Top Left inside padding)
    ctx.fillStyle = "#475569";
    ctx.font = `bold ${Math.max(11, Math.round(drawWidth * 0.02))}px monospace`;
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(`Step ${step.observation.step}`, padding + 6, padding + 6);
  }, [step, width, height, showFleetNum, showProduction, showTrajectories, fleetSizeFilter]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: `${width}px`, height: `${height}px` }}
      className="replay-map-frame rounded-lg border border-border shadow-xs max-w-full"
    />
  );
}
