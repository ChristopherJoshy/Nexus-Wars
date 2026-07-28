"use client";

import { useRef, useEffect } from "react";

const BOARD_SIZE = 100;
const CENTER = BOARD_SIZE / 2;
const SUN_RADIUS = 8.5;

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
  fleetSizeFilter?: "all" | "small" | "medium" | "large";
}

function parsePlanets(raw: number[][]): Planet[] {
  return raw.map((p) => ({
    id: p[0],
    owner: p[1],
    x: p[2],
    y: p[3],
    radius: p[4],
    ships: p[5],
    production: p[6],
    energy: p[7] ?? 100,
    energyCap: p[8] ?? 100,
    energyRegen: p[9] ?? 5,
  }));
}

function parseFleets(raw: number[][]): Fleet[] {
  return raw.map((f) => ({
    id: f[0],
    owner: f[1],
    x: f[2],
    y: f[3],
    angle: f[4],
    from_planet_id: f[5],
    ships: f[6],
    launchedStep: f[7],
  }));
}

export function ReplayRenderer({
  step,
  width = 580,
  height = 580,
  showFleetNum = true,
  showProduction = true,
  fleetSizeFilter = "all",
}: ReplayRendererProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Support High-DPI displays (Retina, 4K)
    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.scale(dpr, dpr);

    // Calculate padding margin so edge planets and text labels never clip
    const padding = Math.max(28, Math.round(width * 0.05));
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
    for (let i = 0; i <= BOARD_SIZE; i += 10) {
      const gx = toScreenX(i);
      const gy = toScreenY(i);
      ctx.beginPath();
      ctx.moveTo(gx, padding);
      ctx.lineTo(gx, height - padding);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(padding, gy);
      ctx.lineTo(width - padding, gy);
      ctx.stroke();
    }

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

    // Render Fleet Trajectory Dashed Lines (Matching Owner Color)
    for (const f of fleets) {
      const originPlanet = planetsMap.get(f.from_planet_id);
      if (originPlanet) {
        const pColors = PLAYER_COLORS[f.owner as keyof typeof PLAYER_COLORS] || PLAYER_COLORS[-1];
        const fx = toScreenX(f.x);
        const fy = toScreenY(f.y);
        const ox = toScreenX(originPlanet.x);
        const oy = toScreenY(originPlanet.y);

        ctx.beginPath();
        ctx.setLineDash([3, 4]);
        ctx.moveTo(ox, oy);
        ctx.lineTo(fx, fy);
        ctx.strokeStyle = pColors.main;
        ctx.globalAlpha = 0.45;
        ctx.lineWidth = 1.2;
        ctx.stroke();
        ctx.globalAlpha = 1.0;
        ctx.setLineDash([]);
      }
    }

    // Render Planet Nodes
    for (const p of planets) {
      const px = toScreenX(p.x);
      const py = toScreenY(p.y);

      const rawR = typeof p.radius === "number" && p.radius > 0 ? p.radius : 2.5;
      const minR = Math.max(11, Math.round(drawWidth * 0.024));
      const maxR = Math.min(34, Math.round(drawWidth * 0.048));
      const pr = Math.min(maxR, Math.max(minR, rawR * scale * 0.65));

      const pColors = PLAYER_COLORS[p.owner as keyof typeof PLAYER_COLORS] || PLAYER_COLORS[-1];

      // Planet Glow Aura for active player planets
      if (p.owner !== -1) {
        ctx.beginPath();
        ctx.arc(px, py, pr + 4, 0, Math.PI * 2);
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
      ctx.font = `bold ${Math.max(10, Math.round(pr * 0.82))}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(p.ships), px, py);

      // Planet Production Badge above node (+P)
      if (showProduction && p.production > 0) {
        const prodText = `+${p.production}`;
        const fontSize = Math.max(9, Math.round(drawWidth * 0.017));
        ctx.font = `bold ${fontSize}px monospace`;
        ctx.fillStyle = "#15803d";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(prodText, px, py - pr - 3);
      }
    }

    // Render Fleets (Arrowhead Triangles + Ship Count Badges)
    const arrowHeadSize = Math.max(6, Math.round(drawWidth * 0.014));
    for (const f of fleets) {
      const fx = toScreenX(f.x);
      const fy = toScreenY(f.y);
      const pColors = PLAYER_COLORS[f.owner as keyof typeof PLAYER_COLORS] || PLAYER_COLORS[-1];
      const angle = f.angle || 0;

      // Draw Fleet Arrowhead in Owner Color
      ctx.fillStyle = pColors.main;
      ctx.strokeStyle = pColors.stroke;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(fx + (arrowHeadSize + 2) * Math.cos(angle), fy + (arrowHeadSize + 2) * Math.sin(angle));
      ctx.lineTo(fx + arrowHeadSize * Math.cos(angle + 2.35), fy + arrowHeadSize * Math.sin(angle + 2.35));
      ctx.lineTo(fx + arrowHeadSize * Math.cos(angle - 2.35), fy + arrowHeadSize * Math.sin(angle - 2.35));
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Render Ship Count Badge on Fleet
      if (showFleetNum) {
        const shipStr = String(f.ships);
        const fontSize = Math.max(9, Math.round(drawWidth * 0.016));
        ctx.font = `bold ${fontSize}px monospace`;
        const textWidth = ctx.measureText(shipStr).width;

        const badgeX = fx;
        const badgeY = fy - arrowHeadSize - 4;
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
  }, [step, width, height, showFleetNum, showProduction, fleetSizeFilter]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: `${width}px`, height: `${height}px` }}
      className="replay-map-frame rounded-lg border border-border shadow-xs max-w-full"
    />
  );
}
