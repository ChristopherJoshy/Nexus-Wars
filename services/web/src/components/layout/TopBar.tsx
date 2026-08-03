"use client";

import { useState, useRef, useEffect } from "react";
import { useSession, signIn, signOut } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { LogOut, User, ChevronDown, Bell } from "lucide-react";

export function TopBar() {
  const { data: session, isPending } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const [liveFeedEnabled, setLiveFeedEnabled] = useState(true);
  const menuRef = useRef<HTMLDivElement>(null);

  const userName = session?.user?.name || session?.user?.email || "User";
  const userEmail = session?.user?.email || "";

  useEffect(() => {
    const stored = localStorage.getItem("nexus_live_feed_enabled");
    if (stored !== null) {
      setLiveFeedEnabled(stored === "true");
    }
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="h-12 bg-card border-b border-border px-6 flex items-center justify-between gap-3 sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <span className="nw-kicker">Nexus Wars</span>
        <span className="h-3 w-px bg-border hidden sm:block" />
        <span className="text-[10px] font-mono text-muted-foreground tracking-wider hidden sm:block">SEASON 01</span>
      </div>

      {/* Right — Auth */}
      <div className="flex items-center gap-3">
        {isPending ? (
          <div className="w-8 h-8 rounded-full bg-muted animate-pulse" />
        ) : !session ? (
          <Button
            size="sm"
            onClick={() => signIn.social({ provider: "google" })}
            className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs px-4 py-1"
          >
            Sign In
          </Button>
        ) : (
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="flex items-center gap-1.5 p-1 rounded-full hover:bg-muted transition-colors cursor-pointer outline-none"
              title={userName}
            >
              {session.user.image ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={session.user.image}
                  alt={userName}
                  className="w-8 h-8 rounded-full object-cover border border-border shadow-xs"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground font-bold text-xs flex items-center justify-center border border-border">
                  {userName[0].toUpperCase()}
                </div>
              )}
              <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${menuOpen ? "rotate-180" : ""}`} />
            </button>

            {menuOpen && (
              <div className="absolute right-0 mt-2 w-52 bg-card border border-border rounded-lg shadow-lg py-2 z-50">
                <div className="px-4 py-2 border-b border-border">
                  <div className="text-xs font-semibold text-foreground truncate flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5 text-primary" />
                    {userName}
                  </div>
                  {userEmail && (
                    <div className="text-[10px] text-muted-foreground font-mono truncate mt-0.5">
                      {userEmail}
                    </div>
                  )}
                </div>

                <div className="p-1 border-b border-border">
                  <button
                    onClick={() => {
                      const next = !liveFeedEnabled;
                      setLiveFeedEnabled(next);
                      localStorage.setItem("nexus_live_feed_enabled", String(next));
                      window.dispatchEvent(new Event("nexus_live_feed_toggle"));
                    }}
                    className="w-full flex items-center justify-between px-3 py-2 text-xs text-foreground hover:bg-muted rounded-md transition-colors cursor-pointer font-medium"
                  >
                    <span className="flex items-center gap-2">
                      <Bell className="w-3.5 h-3.5 text-primary" />
                      Live Notifications
                    </span>
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${liveFeedEnabled ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'}`}>
                      {liveFeedEnabled ? "ON" : "OFF"}
                    </span>
                  </button>
                </div>

                <div className="p-1">
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      signOut();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-destructive hover:bg-muted rounded-md transition-colors cursor-pointer font-medium"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    Log Out
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
