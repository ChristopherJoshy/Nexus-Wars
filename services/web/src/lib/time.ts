import { useEffect, useState } from "react";

export function parseUTC(dateInput: Date | string | number | null | undefined): Date | null {
  if (!dateInput) return null;
  if (dateInput instanceof Date) return isNaN(dateInput.getTime()) ? null : dateInput;
  if (typeof dateInput === "number") {
    const d = new Date(dateInput);
    return isNaN(d.getTime()) ? null : d;
  }
  
  let str = String(dateInput).trim();
  if (!str) return null;
  
  // If string contains space instead of 'T', convert to ISO 'T'
  if (str.includes(" ") && !str.includes("T")) {
    str = str.replace(" ", "T");
  }
  
  // If string does not have timezone offset (+XX:XX or Z), append 'Z' for UTC
  if (!str.endsWith("Z") && !/[+-]\d{2}:?\d{2}$/.test(str)) {
    str += "Z";
  }

  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

export function formatRelativeTime(dateInput: Date | string | number | null | undefined): string {
  const date = parseUTC(dateInput);
  if (!date) return "Just now";

  // Calculate diff strictly in browser local memory against Date.now()
  const nowMs = Date.now();
  const diffMs = Math.max(0, nowMs - date.getTime());
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

// Forces a re-render at a given interval. Used to keep relative time labels fresh.
export function useTick(delay: number) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), delay);
    return () => clearInterval(id);
  }, [delay]);
}
