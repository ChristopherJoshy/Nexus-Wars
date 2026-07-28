"use client";

import { useEffect, useState } from "react";
import { useSession, signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";

interface Team {
  id: string;
  name: string;
  team_code: string;
  owner_id: string | null;
}

export default function TeamPage() {
  const { data: session, isPending: sessionPending } = useSession();
  const [team, setTeam] = useState<Team | null>(null);
  const [teamName, setTeamName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    if (!session) return;
    fetch("/api/teams", {
      headers: { Authorization: `Bearer ${session.token}` },
    })
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error("No team found");
      })
      .then((data) => {
        setError(false);
        setTeam(data);
        setTeamName(data.name || "");
      })
      .catch(() => setTeam(null))
      .finally(() => setLoading(false));
  }, [session]);

  const saveTeamName = async () => {
    if (!session || !teamName) return;
    setError(false);
    try {
      const res = await fetch("/api/teams", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.token}`,
        },
        body: JSON.stringify({ name: teamName }),
      });
      if (res.ok) {
        const updated = await res.json();
        setTeam(updated);
        setSavedSuccess(true);
        setTimeout(() => setSavedSuccess(false), 2500);
      } else {
        throw new Error("Save failed");
      }
    } catch {
      setError(true);
    }
  };

  const joinTeam = async () => {
    if (!session) return;
    setError(false);
    try {
      const res = await fetch("/api/teams/join", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.token}`,
        },
        body: JSON.stringify({ teamCode: joinCode }),
      });
      if (res.ok) {
        const joined = await res.json();
        setTeam(joined);
        setTeamName(joined.name);
      } else {
        throw new Error("Join failed");
      }
    } catch {
      setError(true);
    }
  };

  if (sessionPending || loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-3 font-mono">
        <div className="w-7 h-7 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <span className="text-xs text-muted-foreground uppercase tracking-widest animate-pulse">
          Loading Team Records...
        </span>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-5 text-center max-w-md mx-auto">
        <h2 className="text-xl font-bold text-foreground uppercase">[ ACCESS_DENIED ]</h2>
        <p className="text-muted-foreground text-xs leading-relaxed">
          Authentication is required to view or edit team settings. Please sign in with your Google account.
        </p>
        <Button
          onClick={() => signIn.social({ provider: "google" })}
          className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-6 py-2"
        >
          Sign In with Google
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-8">
      {/* Title Header */}
      <div className="space-y-1">
        <h2 className="text-2xl font-bold text-foreground">Your Team</h2>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Everyone that competes in a Competition does so as a team &mdash; even if you&apos;re competing by yourself.
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-destructive rounded-lg p-3 text-xs">
          [ ERROR ] An error occurred while saving team settings.
        </div>
      )}

      {/* General Section */}
      <div className="space-y-4 pt-2">
        <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">General</h3>

        <div className="space-y-1.5">
          <div className="relative border border-border focus-within:border-primary rounded-lg p-3 bg-card transition-all max-w-lg">
            <label className="absolute -top-2.5 left-3 px-1.5 bg-card text-[10px] font-mono text-muted-foreground uppercase tracking-wider font-semibold">
              Team Name
            </label>
            <input
              type="text"
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              placeholder="Enter your team name"
              className="w-full bg-transparent text-sm text-foreground outline-none font-sans font-medium uppercase"
            />
          </div>
          <span className="text-[11px] text-muted-foreground block pl-1">
            This name appears on the leaderboard.
          </span>
        </div>
      </div>

      {/* Team Members Section */}
      <div className="space-y-4 pt-2 border-t border-border">
        <h3 className="text-sm font-bold text-foreground">Team Members</h3>

        <div className="flex items-center gap-3 bg-muted border border-border p-3 rounded-lg max-w-sm">
          {session.user.image ? (
            <img
              src={session.user.image}
              alt={session.user.name || "Member Avatar"}
              className="w-10 h-10 rounded-full object-cover border border-primary/50"
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-primary/20 text-foreground font-bold flex items-center justify-center border border-primary">
              {(session.user.name || "U")[0].toUpperCase()}
            </div>
          )}

          <div>
            <div className="text-xs font-semibold text-foreground">
              {session.user.name || "Participant"} (You)
            </div>
            <div className="text-[11px] text-muted-foreground">Team Leader</div>
          </div>
        </div>
      </div>

      {/* Invite Code */}
      {team && (
        <div className="space-y-2 pt-2 border-t border-border">
          <h3 className="text-sm font-bold text-foreground">Invite Code</h3>
          <p className="text-xs text-muted-foreground">Share this code with teammates to join your team.</p>
          <div className="bg-muted border border-border p-4 rounded-lg max-w-sm text-center">
            <span className="font-mono text-xl font-bold tracking-widest text-primary select-all">
              {team.team_code}
            </span>
          </div>
        </div>
      )}

      {/* Join Team */}
      {!team && (
        <div className="space-y-3 pt-2 border-t border-border max-w-sm">
          <h3 className="text-sm font-bold text-foreground">Join a Team</h3>
          <p className="text-xs text-muted-foreground">Enter a 6-character invite code to join an existing team.</p>
          <input
            type="text"
            maxLength={6}
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            placeholder="6-LETTER CODE"
            className="w-full bg-card border border-border focus:border-primary p-2.5 rounded-lg text-xs font-mono text-center uppercase tracking-widest text-foreground outline-none"
          />
          <button
            type="button"
            onClick={joinTeam}
            disabled={joinCode.length !== 6}
            className="w-full nexus-pill border border-border text-foreground hover:bg-muted justify-center py-2 text-xs"
          >
            Join Team
          </button>
        </div>
      )}

      {/* Save */}
      <div className="pt-4 border-t border-border flex items-center gap-3">
        <button
          type="button"
          onClick={saveTeamName}
          disabled={!teamName}
          className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-6 py-2 text-xs"
        >
          Save Changes
        </button>

        {savedSuccess && (
          <span className="text-xs text-emerald-700 font-medium animate-fade-in">
            Team updated successfully!
          </span>
        )}
      </div>
    </div>
  );
}
