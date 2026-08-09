"use client";

import { useState, useEffect } from "react";
import { useSession } from "@/lib/auth-client";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Download, Table as TableIcon } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface TeamAdminRecord {
  id: string;
  rank: number;
  name: string;
  collegeName: string;
  teamMembersInfo: string;
  mobileNumbers: string;
  rating: number;
  createdAt: string;
}

export default function AdminPage() {
  const { data: session, isPending } = useSession();
  const router = useRouter();
  const [paused, setPaused] = useState(false);
  const [teams, setTeams] = useState<TeamAdminRecord[]>([]);
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
          setTeams(data.teams || []);
          setLoaded(true);
        }
      } catch {
        if (!cancelled) setError("Failed to load admin data");
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

  const exportCSV = () => {
    if (teams.length === 0) return;
    const headers = ["Rank", "Team Name", "College Name", "Team Members", "Mobile Numbers", "Elo Rating", "Created At"];
    const rows = teams.map((t) => [
      t.rank,
      `"${t.name.replace(/"/g, '""')}"`,
      `"${(t.collegeName || "").replace(/"/g, '""')}"`,
      `"${(t.teamMembersInfo || "").replace(/"/g, '""')}"`,
      `"${(t.mobileNumbers || "").replace(/"/g, '""')}"`,
      t.rating,
      `"${t.createdAt}"`,
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "registered-teams-contact-info.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (isPending || !loaded) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center space-y-3 font-mono">
          <div className="w-7 h-7 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-xs text-muted-foreground uppercase tracking-widest animate-pulse">
            Loading Admin Configuration...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-6 space-y-8">
      <div className="max-w-6xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground mb-1">Admin Panel</h1>
          <p className="text-muted-foreground text-xs font-mono">
            Signed in as <span className="text-primary">{session?.user?.email}</span>
          </p>
        </div>

        {error && (
          <div className="bg-destructive/10 border border-destructive/30 text-destructive px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Submissions Control Card */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-6 shadow-sm">
          <div>
            <h2 className="text-lg font-semibold text-foreground mb-1">Submissions Control</h2>
            <p className="text-muted-foreground text-xs">
              Pause all new submissions while keeping matchmaking active.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className={`px-3 py-1 rounded-full text-xs font-mono font-medium ${
              paused
                ? "bg-red-500/10 text-red-400 border border-red-500/30"
                : "bg-green-500/10 text-green-400 border border-green-500/30"
            }`}>
              {paused ? "PAUSED" : "ACTIVE"}
            </div>

            <Button
              onClick={togglePause}
              loading={toggling}
              disabled={toggling}
              className={`px-5 py-2 rounded-lg text-xs font-medium transition-colors ${
                paused
                  ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                  : "bg-destructive hover:bg-destructive/90 text-white"
              }`}
            >
              {paused ? "Resume Submissions" : "Pause Submissions"}
            </Button>
          </div>
        </div>

        {/* Registered Teams & Contact Information Table */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-6 shadow-sm">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div className="flex items-center gap-2">
              <TableIcon className="w-5 h-5 text-primary" />
              <div>
                <h2 className="text-lg font-semibold text-foreground">Registered Teams Contact Info</h2>
                <p className="text-xs text-muted-foreground">
                  College names, team members, and contact numbers submitted by participants.
                </p>
              </div>
            </div>

            <Button
              onClick={exportCSV}
              disabled={teams.length === 0}
              className="nexus-pill bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-4 py-2 text-xs"
            >
              <Download className="w-4 h-4 mr-1.5" />
              Export CSV
            </Button>
          </div>

          <div className="border border-border rounded-lg overflow-x-auto">
            <Table>
              <TableHeader className="bg-muted border-b border-border">
                <TableRow>
                  <TableHead className="w-12 text-center text-xs">#</TableHead>
                  <TableHead className="text-xs font-semibold">Team Name</TableHead>
                  <TableHead className="text-xs font-semibold">College / Institution</TableHead>
                  <TableHead className="text-xs font-semibold">Team Members</TableHead>
                  <TableHead className="text-xs font-semibold">Mobile Numbers</TableHead>
                  <TableHead className="w-20 text-right text-xs">Elo Rating</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {teams.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-xs font-mono text-muted-foreground">
                      No team records found.
                    </TableCell>
                  </TableRow>
                ) : (
                  teams.map((t) => (
                    <TableRow key={t.id} className="border-b border-border hover:bg-muted/50 transition-colors">
                      <TableCell className="font-mono text-xs text-center font-bold text-muted-foreground">{t.rank}</TableCell>
                      <TableCell className="font-sans text-xs font-bold text-foreground">{t.name}</TableCell>
                      <TableCell className="font-sans text-xs text-muted-foreground">{t.collegeName}</TableCell>
                      <TableCell className="font-sans text-xs text-muted-foreground whitespace-pre-line">{t.teamMembersInfo}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{t.mobileNumbers}</TableCell>
                      <TableCell className="font-mono text-xs font-bold text-right text-primary">{t.rating}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </div>
  );
}
