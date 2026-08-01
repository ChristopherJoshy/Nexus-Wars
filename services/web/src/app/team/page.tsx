"use client";

import { useEffect, useState } from "react";
import { useSession, signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";

interface TeamMember {
  userId: string;
  role: string;
  joinedAt: string;
  name: string | null;
  email: string | null;
  image: string | null;
}

interface Team {
  id: string;
  name: string;
  team_code: string;
  owner_id: string | null;
  members: TeamMember[];
}

export default function TeamPage() {
  const { data: session, isPending: sessionPending } = useSession();
  const [team, setTeam] = useState<Team | null>(null);
  const [teamName, setTeamName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [savedSuccess, setSavedSuccess] = useState(false);

  const currentUserMember = team?.members?.find((m) =>
    (m.email && session?.user?.email && m.email.toLowerCase() === session.user.email.toLowerCase()) ||
    m.userId === session?.user?.id
  );

  const isOwner =
    !team ||
    (currentUserMember
      ? currentUserMember.role === "owner"
      : team.owner_id === session?.user?.id);

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
        setErrorMsg(null);
        setTeam(data);
        setTeamName(data.name || "");
      })
      .catch(() => setTeam(null))
      .finally(() => setLoading(false));
  }, [session]);

  const saveTeamName = async () => {
    if (!session || !teamName || (team && !isOwner)) return;
    setErrorMsg(null);
    setSubmitting(true);
    try {
      const method = team ? "PATCH" : "POST";
      const res = await fetch("/api/teams", {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.token}`,
        },
        body: JSON.stringify({ name: teamName }),
      });
      if (res.ok) {
        const updated = await res.json();
        setTeam(updated);
        setTeamName(updated.name || "");
        setSavedSuccess(true);
        setTimeout(() => setSavedSuccess(false), 2500);
      } else {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || "Save failed");
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "An error occurred while saving team settings.");
    } finally {
      setSubmitting(false);
    }
  };

  const joinTeam = async () => {
    if (!session) return;
    setErrorMsg(null);
    setSubmitting(true);
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
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || "Join failed");
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "An error occurred while joining team.");
    } finally {
      setSubmitting(false);
    }
  };

  if (sessionPending || (session && loading)) {
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
      <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-5 text-center max-w-md mx-auto font-mono">
        <h2 className="text-xl font-bold text-foreground uppercase">[ LOGIN_REQUIRED ]</h2>
        <p className="text-muted-foreground text-xs leading-relaxed">
          Authentication is required to view or manage team settings. Please sign in to continue.
        </p>
        <Button
          onClick={() => signIn.social({ provider: "google" })}
          className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-6 py-2 cursor-pointer active:scale-95"
        >
          Sign In with Google
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-foreground">Team Management</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Manage your team name or join an existing team via invite code.
        </p>
      </div>

      {savedSuccess && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400 rounded-lg p-3 text-xs font-mono">
          [ SUCCESS ] Team settings saved successfully.
        </div>
      )}

      {errorMsg && (
        <div className="bg-destructive/10 border border-destructive/30 text-destructive rounded-lg p-3 text-xs font-mono">
          [ ERROR ] {errorMsg}
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
              disabled={team !== null && !isOwner}
              onChange={(e) => setTeamName(e.target.value)}
              placeholder="Enter your team name"
              className="w-full bg-transparent text-sm text-foreground outline-none font-sans font-medium uppercase disabled:opacity-60 disabled:cursor-not-allowed"
            />
          </div>
          {team && !isOwner ? (
            <span className="text-[11px] text-amber-500/90 font-mono block pl-1">
              [ NOTE ] Only team leaders can edit the team name.
            </span>
          ) : (
            <span className="text-[11px] text-muted-foreground block pl-1">
              This name appears on the leaderboard.
            </span>
          )}
        </div>
      </div>

      {/* Team Members Section */}
      {team && team.members && (
        <div className="space-y-4 pt-2 border-t border-border">
          <h3 className="text-sm font-bold text-foreground">Team Members</h3>

          <div className="space-y-2 max-w-sm">
            {team.members.map((member) => {
              const isCurrentUser =
                (member.email && session.user.email && member.email.toLowerCase() === session.user.email.toLowerCase()) ||
                member.userId === session.user.id;

              return (
                <div
                  key={member.userId}
                  className="flex items-center gap-3 bg-muted border border-border p-3 rounded-lg"
                >
                  {member.image ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={member.image}
                      alt={member.name || "Member Avatar"}
                      className="w-10 h-10 rounded-full object-cover border border-primary/50"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-primary/20 text-foreground font-bold flex items-center justify-center border border-primary">
                      {(member.name || "U")[0].toUpperCase()}
                    </div>
                  )}

                  <div>
                    <div className="text-xs font-semibold text-foreground">
                      {member.name || "Participant"}
                      {isCurrentUser && (
                        <span className="text-muted-foreground"> (You)</span>
                      )}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {member.role === "owner" ? "Team Leader" : "Member"}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
          <Button
            onClick={joinTeam}
            loading={submitting}
            disabled={joinCode.length !== 6 || submitting}
            className="w-full nexus-pill border border-border text-foreground hover:bg-muted justify-center py-2 text-xs"
          >
            Join Team
          </Button>
        </div>
      )}

      {/* Save */}
      <div className="pt-4 border-t border-border flex items-center gap-3">
        <Button
          onClick={saveTeamName}
          loading={submitting}
          disabled={!teamName || submitting || (team !== null && !isOwner)}
          className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-6 py-2 text-xs disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {team ? "Save Changes" : "Create Team"}
        </Button>
      </div>
    </div>
  );
}
