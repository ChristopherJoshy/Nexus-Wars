"use client";

import React, { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

type FeedEvent = {
  id: string;
  status: "running" | "finished";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  team_a_name: string;
  team_b_name: string;
  team_a_photo: string;
  team_b_photo: string;
  team_a_elo: number;
  team_b_elo: number;
  winner: string | null;
  rating_change_a: number | null;
  rating_change_b: number | null;
};

type Toast = {
  toastId: string;
  event: FeedEvent;
  type: "start" | "end";
};

export default function LiveFeed() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const knownEventsRef = useRef<Record<string, string>>({});
  const initialLoadRef = useRef(true);

  useEffect(() => {
    const checkSettings = () => {
      const stored = localStorage.getItem("nexus_live_feed_enabled");
      setEnabled(stored !== "false");
      setIsMobile(window.innerWidth < 768);
    };

    checkSettings();
    window.addEventListener("nexus_live_feed_toggle", checkSettings);
    window.addEventListener("resize", checkSettings);

    return () => {
      window.removeEventListener("nexus_live_feed_toggle", checkSettings);
      window.removeEventListener("resize", checkSettings);
    };
  }, []);

  useEffect(() => {
    if (!enabled || isMobile) return;

    const fetchFeed = async () => {
      try {
        const res = await fetch("/api/live_feed?t=" + Date.now());
        if (!res.ok) return;
        const data = await res.json();
        
        if (!data.events || !Array.isArray(data.events)) return;

        const newToasts: Toast[] = [];
        
        data.events.forEach((ev: FeedEvent) => {
          const knownStatus = knownEventsRef.current[ev.id];
          
          if (initialLoadRef.current) {
            knownEventsRef.current[ev.id] = ev.status;
          } else {
            if (!knownStatus && ev.status === "running") {
              newToasts.push({ toastId: Math.random().toString(), event: ev, type: "start" });
              knownEventsRef.current[ev.id] = ev.status;
            } else if (knownStatus === "running" && ev.status === "finished") {
              newToasts.push({ toastId: Math.random().toString(), event: ev, type: "end" });
              knownEventsRef.current[ev.id] = ev.status;
            } else if (!knownStatus && ev.status === "finished") {
              newToasts.push({ toastId: Math.random().toString(), event: ev, type: "end" });
              knownEventsRef.current[ev.id] = ev.status;
            }
          }
        });

        initialLoadRef.current = false;
        
        if (newToasts.length > 0) {
          setToasts(prev => [...prev, ...newToasts]);
          
          newToasts.forEach(t => {
            setTimeout(() => {
              setToasts(prev => prev.filter(p => p.toastId !== t.toastId));
            }, 8000);
          });
        }

      } catch (err) {
        console.error("LiveFeed fetch error:", err);
      }
    };

    fetchFeed();
    const interval = setInterval(fetchFeed, 5000);
    return () => clearInterval(interval);
  }, [enabled, isMobile]);

  if (!enabled || isMobile) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2.5 pointer-events-none hidden md:flex">
      <AnimatePresence>
        {toasts.slice(-3).map((toast) => (
          <motion.div
            key={toast.toastId}
            initial={{ opacity: 0, y: 30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: "spring", stiffness: 350, damping: 25 }}
            className="pointer-events-auto"
          >
            <ToastCard toast={toast} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function ToastCard({ toast }: { toast: Toast }) {
  const { event, type } = toast;
  
  const isEnd = type === "end";
  let aChange = "";
  let bChange = "";
  
  if (isEnd) {
    if (event.rating_change_a! > 0) aChange = `+${Math.round(event.rating_change_a!)}`;
    else aChange = `${Math.round(event.rating_change_a! || 0)}`;
    
    if (event.rating_change_b! > 0) bChange = `+${Math.round(event.rating_change_b!)}`;
    else bChange = `${Math.round(event.rating_change_b! || 0)}`;
  }

  // Postgres enum uses 'a' and 'b'
  const aWon = isEnd && (event.winner === "team_a" || event.winner === "a");
  const bWon = isEnd && (event.winner === "team_b" || event.winner === "b");

  return (
    <div className="w-80 bg-card border border-border rounded-lg shadow-2xl p-3 font-sans opacity-100 text-foreground bg-[#fffdf8]">
      {/* Header Bar */}
      <div className="flex items-center justify-between border-b border-border/70 pb-1.5 mb-2">
        <span className="text-[10px] font-bold tracking-widest uppercase text-primary flex items-center gap-1">
          {isEnd ? "⚡ MATCH RESULT" : "⚔️ MATCH STARTING"}
        </span>
        {isEnd && (
          <span className="text-[10px] font-mono text-muted-foreground font-semibold bg-muted px-1.5 py-0.5 rounded border border-border/50">
            {aChange} / {bChange}
          </span>
        )}
      </div>

      {/* Matchup */}
      <div className="flex items-center justify-between gap-2">
        {/* Team A */}
        <div className={`flex items-center gap-2 flex-1 min-w-0 ${isEnd && !aWon ? "opacity-50" : ""}`}>
          {event.team_a_photo ? (
            <img src={event.team_a_photo} alt="" className="w-7 h-7 rounded-full border border-border shrink-0 object-cover" />
          ) : (
            <div className="w-7 h-7 rounded-full bg-primary/10 text-primary font-bold text-xs flex items-center justify-center border border-border shrink-0">
              {event.team_a_name[0]?.toUpperCase()}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1">
              <span className={`text-xs truncate ${aWon ? "font-black text-primary" : "font-semibold text-foreground"}`}>
                {event.team_a_name}
              </span>
            </div>
            {aWon && (
              <span className="inline-flex items-center gap-0.5 text-[9px] font-black text-primary leading-none uppercase bg-primary/10 px-1 py-0.5 rounded border border-primary/20 mt-0.5">
                👑 WINNER
              </span>
            )}
          </div>
        </div>

        {/* VS Divider */}
        <div className="px-2 py-1 rounded bg-muted border border-border text-[10px] font-mono font-black text-muted-foreground shrink-0">
          VS
        </div>

        {/* Team B */}
        <div className={`flex items-center justify-end gap-2 flex-1 min-w-0 text-right ${isEnd && !bWon ? "opacity-50" : ""}`}>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-end gap-1">
              <span className={`text-xs truncate ${bWon ? "font-black text-primary" : "font-semibold text-foreground"}`}>
                {event.team_b_name}
              </span>
            </div>
            {bWon && (
              <span className="inline-flex items-center gap-0.5 text-[9px] font-black text-primary leading-none uppercase bg-primary/10 px-1 py-0.5 rounded border border-primary/20 mt-0.5">
                👑 WINNER
              </span>
            )}
          </div>
          {event.team_b_photo ? (
            <img src={event.team_b_photo} alt="" className="w-7 h-7 rounded-full border border-border shrink-0 object-cover" />
          ) : (
            <div className="w-7 h-7 rounded-full bg-primary/10 text-primary font-bold text-xs flex items-center justify-center border border-border shrink-0">
              {event.team_b_name[0]?.toUpperCase()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
