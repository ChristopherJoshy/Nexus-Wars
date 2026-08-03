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

  // Determine winners
  const aWon = isEnd && event.winner === "team_a";
  const bWon = isEnd && event.winner === "team_b";
  const aLost = isEnd && event.winner === "team_b";
  const bLost = isEnd && event.winner === "team_a";

  const titleText = isEnd ? "MATCH RESULT" : "MATCH STARTING";
  const titleColor = isEnd ? "text-primary" : "text-muted-foreground";

  return (
    <div className="flex flex-col items-center drop-shadow-sm font-sans mb-1">
      <div className={`text-[9px] tracking-[0.2em] font-bold uppercase mb-0.5 ${titleColor}`}>
        {titleText}
      </div>
      
      <div className="flex items-center h-10 bg-transparent">
        
        {/* LEFT WING */}
        <div 
          className={`relative h-full w-36 flex items-center justify-start pl-3 overflow-hidden bg-card transition-all ${aLost ? 'opacity-60 grayscale' : ''}`}
          style={{ clipPath: "polygon(0 0, 100% 0, 85% 100%, 0 100%)" }}
        >
          {event.team_a_photo ? (
            <img src={event.team_a_photo} alt="" className="w-5 h-5 rounded-full border border-border mr-1.5 shrink-0 object-cover" />
          ) : (
            <div className="w-5 h-5 rounded-full border border-border mr-1.5 shrink-0 bg-secondary" />
          )}
          <span className={`relative z-10 text-foreground truncate max-w-[70px] text-xs ${aWon ? 'font-black' : 'font-semibold'}`}>
            {aWon && "👑 "}{event.team_a_name}
          </span>
        </div>

        {/* CENTER DIAMOND */}
        <div 
          className="relative h-[115%] w-16 flex flex-col items-center justify-center bg-primary text-primary-foreground -mx-5 z-10 shadow-sm"
          style={{ clipPath: "polygon(20% 0, 100% 0, 80% 100%, 0 100%)" }}
        >
          <span className="font-black italic text-xs leading-none mt-0.5">VS</span>
          {isEnd && (
            <span className="text-[8px] font-bold text-primary-foreground/90 mt-0.5">
              {aChange}/{bChange}
            </span>
          )}
        </div>

        {/* RIGHT WING */}
        <div 
          className={`relative h-full w-36 flex items-center justify-end pr-3 overflow-hidden bg-card transition-all ${bLost ? 'opacity-60 grayscale' : ''}`}
          style={{ clipPath: "polygon(15% 0, 100% 0, 100% 100%, 0 100%)" }}
        >
          <span className={`relative z-10 text-foreground truncate max-w-[70px] text-right text-xs ${bWon ? 'font-black' : 'font-semibold'}`}>
            {event.team_b_name}{bWon && " 👑"}
          </span>
          {event.team_b_photo ? (
            <img src={event.team_b_photo} alt="" className="w-5 h-5 rounded-full border border-border ml-1.5 shrink-0 object-cover" />
          ) : (
            <div className="w-5 h-5 rounded-full border border-border ml-1.5 shrink-0 bg-secondary" />
          )}
        </div>
        
      </div>
    </div>
  );
}
