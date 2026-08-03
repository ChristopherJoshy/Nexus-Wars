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
  const knownEventsRef = useRef<Record<string, string>>({});
  const initialLoadRef = useRef(true);

  useEffect(() => {
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
            // Just record it, don't toast on initial load
            knownEventsRef.current[ev.id] = ev.status;
          } else {
            if (!knownStatus && ev.status === "running") {
              newToasts.push({ toastId: Math.random().toString(), event: ev, type: "start" });
              knownEventsRef.current[ev.id] = ev.status;
            } else if (knownStatus === "running" && ev.status === "finished") {
              newToasts.push({ toastId: Math.random().toString(), event: ev, type: "end" });
              knownEventsRef.current[ev.id] = ev.status;
            } else if (!knownStatus && ev.status === "finished") {
              // Missed the start, just show the end
              newToasts.push({ toastId: Math.random().toString(), event: ev, type: "end" });
              knownEventsRef.current[ev.id] = ev.status;
            }
          }
        });

        initialLoadRef.current = false;
        
        if (newToasts.length > 0) {
          setToasts(prev => [...prev, ...newToasts]);
          
          // Auto dismiss after 8 seconds
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
  }, []);

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none hidden md:flex">
      <AnimatePresence>
        {toasts.slice(-3).map((toast) => (
          <motion.div
            key={toast.toastId}
            initial={{ opacity: 0, x: 80, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.85, x: 40 }}
            transition={{ type: "spring", stiffness: 350, damping: 26 }}
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

  // Determine winners (Postgres enum uses 'a' and 'b')
  const aWon = isEnd && (event.winner === "team_a" || event.winner === "a");
  const bWon = isEnd && (event.winner === "team_b" || event.winner === "b");
  const aLost = isEnd && (event.winner === "team_b" || event.winner === "b");
  const bLost = isEnd && (event.winner === "team_a" || event.winner === "a");

  const titleText = isEnd ? "MATCH RESULT" : "MATCH STARTING";
  const titleColor = isEnd ? "text-emerald-700 font-bold" : "text-amber-700 font-bold";

  return (
    <div className="flex flex-col items-center drop-shadow-lg font-sans">
      <div className={`text-[9px] tracking-[0.2em] uppercase mb-0.5 ${titleColor}`}>
        {titleText}
      </div>
      
      <div className="flex items-center h-12 bg-transparent">
        
        {/* LEFT WING */}
        <div 
          className={`relative h-full w-40 flex items-center justify-start pl-3 pr-2 overflow-hidden bg-slate-900 border border-slate-700/50 shadow-inner transition-all ${aLost ? 'opacity-40 grayscale' : ''}`}
          style={{ clipPath: "polygon(0 0, 100% 0, 85% 100%, 0 100%)" }}
        >
          {event.team_a_photo ? (
            <div 
              className="absolute inset-0 bg-cover bg-center" 
              style={{ backgroundImage: `url(${event.team_a_photo})` }}
            />
          ) : (
            <div className="absolute inset-0 bg-slate-800" />
          )}
          {/* Tint overlay for contrast */}
          <div className="absolute inset-0 bg-gradient-to-r from-slate-950/85 via-slate-900/75 to-slate-950/85" />

          <div className="relative z-10 flex flex-col items-start min-w-0 pr-2">
            {aWon && (
              <span className="text-[8px] font-black text-amber-300 tracking-wider flex items-center gap-0.5 bg-amber-950/80 px-1 rounded border border-amber-500/40 leading-none mb-0.5">
                👑 WINNER
              </span>
            )}
            <span className={`text-white truncate max-w-[85px] text-xs drop-shadow ${aWon ? 'font-black text-amber-200' : 'font-semibold'}`}>
              {event.team_a_name}
            </span>
          </div>
        </div>

        {/* CENTER DIAMOND */}
        <div 
          className="relative h-[115%] w-18 flex flex-col items-center justify-center bg-emerald-800 text-amber-100 -mx-5 z-20 shadow-md border-x border-emerald-600/40"
          style={{ clipPath: "polygon(20% 0, 100% 0, 80% 100%, 0 100%)" }}
        >
          <span className="font-black italic text-xs leading-none">VS</span>
          {isEnd && (
            <span className="text-[8.5px] font-extrabold text-amber-200 tracking-tighter mt-0.5">
              {aChange}/{bChange}
            </span>
          )}
        </div>

        {/* RIGHT WING */}
        <div 
          className={`relative h-full w-40 flex items-center justify-end pr-3 pl-2 overflow-hidden bg-slate-900 border border-slate-700/50 shadow-inner transition-all ${bLost ? 'opacity-40 grayscale' : ''}`}
          style={{ clipPath: "polygon(15% 0, 100% 0, 100% 100%, 0 100%)" }}
        >
          {event.team_b_photo ? (
            <div 
              className="absolute inset-0 bg-cover bg-center" 
              style={{ backgroundImage: `url(${event.team_b_photo})` }}
            />
          ) : (
            <div className="absolute inset-0 bg-slate-800" />
          )}
          {/* Tint overlay for contrast */}
          <div className="absolute inset-0 bg-gradient-to-l from-slate-950/85 via-slate-900/75 to-slate-950/85" />

          <div className="relative z-10 flex flex-col items-end min-w-0 pl-2 text-right">
            {bWon && (
              <span className="text-[8px] font-black text-amber-300 tracking-wider flex items-center gap-0.5 bg-amber-950/80 px-1 rounded border border-amber-500/40 leading-none mb-0.5">
                👑 WINNER
              </span>
            )}
            <span className={`text-white truncate max-w-[85px] text-xs drop-shadow ${bWon ? 'font-black text-amber-200' : 'font-semibold'}`}>
              {event.team_b_name}
            </span>
          </div>
        </div>
        
      </div>
    </div>
  );
}
