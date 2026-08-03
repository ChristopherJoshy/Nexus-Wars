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
        const res = await fetch("https://16-170-239-106.sslip.io/nexus-replays/live_feed.json?t=" + Date.now());
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
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-3 pointer-events-none hidden md:flex">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.toastId}
            initial={{ opacity: 0, x: 100, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8, x: 50 }}
            transition={{ type: "spring", stiffness: 300, damping: 25 }}
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

  const titleText = isEnd ? "MATCH RESULT" : "MATCH STARTING";
  const titleColor = isEnd ? "text-emerald-400" : "text-amber-400";

  return (
    <div className="flex flex-col items-center drop-shadow-2xl font-sans">
      <div className={`text-[10px] tracking-[0.2em] font-bold uppercase mb-1 ${titleColor} drop-shadow-[0_0_8px_rgba(255,255,255,0.3)]`}>
        {titleText}
      </div>
      
      <div className="flex items-center h-16 bg-transparent">
        
        {/* LEFT WING */}
        <div 
          className="relative h-full w-40 flex items-center justify-center overflow-hidden bg-slate-900 border border-slate-700/50"
          style={{ clipPath: "polygon(0 0, 100% 0, 85% 100%, 0 100%)" }}
        >
          {event.team_a_photo && (
            <div 
              className="absolute inset-0 bg-cover bg-center opacity-30 mix-blend-luminosity" 
              style={{ backgroundImage: `url(${event.team_a_photo})` }}
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-r from-slate-900/80 to-transparent" />
          <span className="relative z-10 font-bold text-white truncate max-w-[100px] pl-2 drop-shadow-md">
            {event.team_a_name}
          </span>
        </div>

        {/* CENTER DIAMOND */}
        <div 
          className="relative h-[115%] w-24 flex flex-col items-center justify-center bg-gradient-to-br from-indigo-600 to-purple-800 -mx-6 z-10 border border-indigo-400/30 shadow-[0_0_15px_rgba(79,70,229,0.5)]"
          style={{ clipPath: "polygon(20% 0, 100% 0, 80% 100%, 0 100%)" }}
        >
          <span className="text-white font-black italic text-lg leading-tight mt-1">VS</span>
          {isEnd && (
            <span className="text-[10px] font-bold text-emerald-200 mt-0.5">
              {aChange} / {bChange}
            </span>
          )}
        </div>

        {/* RIGHT WING */}
        <div 
          className="relative h-full w-40 flex items-center justify-center overflow-hidden bg-slate-900 border border-slate-700/50"
          style={{ clipPath: "polygon(15% 0, 100% 0, 100% 100%, 0 100%)" }}
        >
          {event.team_b_photo && (
            <div 
              className="absolute inset-0 bg-cover bg-center opacity-30 mix-blend-luminosity" 
              style={{ backgroundImage: `url(${event.team_b_photo})` }}
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-l from-slate-900/80 to-transparent" />
          <span className="relative z-10 font-bold text-white truncate max-w-[100px] pr-2 drop-shadow-md">
            {event.team_b_name}
          </span>
        </div>
        
      </div>
    </div>
  );
}
