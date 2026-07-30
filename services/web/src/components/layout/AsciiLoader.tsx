"use client";

import { useEffect, useState } from "react";

const ASCII_ART = `
 _   _ _____  ___   _ ___   __        ___  ____  ____  
| \\ | | ____|\\ \\ \\ / // ___|  \\ \\      / / \\|  _ \\/ ___| 
|  \\| |  _|   \\ \\ V /| |  _    \\ \\ /\\ / / _ \\ |_) \\___ \\ 
| |\\  | |___   /   \\ | |_| |    \\ V  V / ___ \\|  _ <___) |
|_| \\_|_____| /_/\\_\\\\ \\____|     \\_/\\_/_/   \\_\\_| \\_\\____/ 
`;

export function AsciiLoader() {
  const [visible, setVisible] = useState(() => {
    if (typeof window !== "undefined") {
      const navEntries = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
      const isReload = navEntries.length > 0 && navEntries[0].type === "reload";
      const isFirstVisit = !sessionStorage.getItem("nexus_visited");
      return isReload || isFirstVisit;
    }
    return false;
  });
  const [fading, setFading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    if (!visible) return;

    if (typeof window !== "undefined") {
      sessionStorage.setItem("nexus_visited", "1");
    }

    const bootSequence = [
      "[ SYS ] INITIALIZING NEXUS KERNEL 2026...",
      "[ NET ] ESTABLISHING HIGH-SPEED MESH CONNECTION...",
      "[ SIM ] LOADING TACTICAL ENGINE ENGINE_V1...",
      "[ OK  ] ALL SYSTEMS OPERATIONAL. READY.",
    ];

    bootSequence.forEach((line, idx) => {
      setTimeout(() => {
        setLogs((prev) => [...prev, line]);
      }, 200 + idx * 250);
    });

    const fadeTimer = setTimeout(() => {
      setFading(true);
    }, 1400);

    const removeTimer = setTimeout(() => {
      setVisible(false);
    }, 1800);

    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      className={`fixed inset-0 z-50 bg-background text-foreground font-mono flex flex-col items-center justify-center p-4 transition-opacity duration-500 select-none ${
        fading ? "opacity-0 pointer-events-none" : "opacity-100"
      }`}
    >
      <div className="max-w-xl w-full flex flex-col items-center space-y-4">
        <pre className="text-[10px] sm:text-xs leading-none text-primary font-mono text-center overflow-hidden font-bold tracking-tighter sm:tracking-normal whitespace-pre">
          {ASCII_ART}
        </pre>
        <div className="w-full h-px bg-border my-2" />
        <div className="w-full space-y-1 text-[11px] text-muted-foreground font-mono text-left pl-2">
          {logs.map((log, index) => (
            <div key={index} className="flex items-center gap-2 animate-in fade-in-50 duration-150">
              <span className="text-emerald-500">&gt;</span>
              <span>{log}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
