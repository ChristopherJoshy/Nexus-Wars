"use client";

import { useState, useEffect } from "react";
import { useSession } from "@/lib/auth-client";
import { useRouter } from "next/navigation";

export default function AdminPage() {
  const { data: session, isPending } = useSession();
  const router = useRouter();
  const [paused, setPaused] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isPending) return;
    if (!session) {
      router.push("/");
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/admin", {
          headers: { Authorization: `Bearer ${session.token}` },
        });
        if (res.status === 403) { router.push("/"); return; }
        if (!cancelled) {
          const data = await res.json();
          setPaused(data.submissionsPaused);
          setLoaded(true);
        }
      } catch {
        if (!cancelled) setError("Failed to load status");
      }
    })();
    return () => { cancelled = true; };
  }, [session, isPending, router]);

  const togglePause = async () => {
    setToggling(true);
    try {
      const res = await fetch("/api/admin", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.token}`,
        },
        body: JSON.stringify({ submissionsPaused: !paused }),
      });
      if (res.status === 403) { router.push("/"); return; }
      const data = await res.json();
      setPaused(data.submissionsPaused);
    } catch {
      setError("Failed to toggle");
    } finally {
      setToggling(false);
    }
  };

  if (isPending || !loaded) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold text-foreground mb-2">Admin Panel</h1>
        <p className="text-muted-foreground text-sm mb-8">
          Signed in as {session?.user?.email}
        </p>

        {error && (
          <div className="bg-destructive/10 border border-destructive/30 text-destructive px-4 py-3 rounded-lg mb-6 text-sm">
            {error}
          </div>
        )}

        <div className="bg-card border border-border rounded-xl p-6 space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-foreground mb-1">Submissions</h2>
            <p className="text-muted-foreground text-sm">
              Pause all new submissions while keeping matchmaking active.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className={`px-3 py-1 rounded-full text-sm font-medium ${
              paused
                ? "bg-red-500/10 text-red-400 border border-red-500/30"
                : "bg-green-500/10 text-green-400 border border-green-500/30"
            }`}>
              {paused ? "PAUSED" : "ACTIVE"}
            </div>

            <button
              onClick={togglePause}
              disabled={toggling}
              className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
                paused
                  ? "bg-green-600 hover:bg-green-700 text-white"
                  : "bg-red-600 hover:bg-red-700 text-white"
              } disabled:opacity-50`}
            >
              {toggling ? "..." : paused ? "Resume Submissions" : "Pause Submissions"}
            </button>
          </div>

          <p className="text-xs text-muted-foreground">
            When paused, users will receive a &ldquo;Submissions are currently paused&rdquo; error when submitting.
          </p>
        </div>
      </div>
    </div>
  );
}
