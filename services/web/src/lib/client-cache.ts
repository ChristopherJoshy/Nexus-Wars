// Client-side in-memory cache for instant UI transitions and 0-ms replay switching

/* eslint-disable @typescript-eslint/no-explicit-any */

class ClientCacheManager {
  private replayCache = new Map<string, any>();
  private matchListCache = new Map<string, { data: any[]; timestamp: number }>();
  private leaderboardCache: { data: any[]; timestamp: number } | null = null;

  // Replays (immutable after match completes)
  getReplay(matchId: string): any | undefined {
    return this.replayCache.get(matchId);
  }

  setReplay(matchId: string, data: any): void {
    this.replayCache.set(matchId, data);
  }

  // Match Lists (cached for 15 seconds)
  getMatchList(key: string, maxAgeMs = 15000): any[] | undefined {
    const entry = this.matchListCache.get(key);
    if (!entry) return undefined;
    if (Date.now() - entry.timestamp > maxAgeMs) return undefined;
    return entry.data;
  }

  setMatchList(key: string, data: any[]): void {
    this.matchListCache.set(key, { data, timestamp: Date.now() });
  }

  // Leaderboard (cached for 15 seconds)
  getLeaderboard(maxAgeMs = 15000): any[] | undefined {
    if (!this.leaderboardCache) return undefined;
    if (Date.now() - this.leaderboardCache.timestamp > maxAgeMs) return undefined;
    return this.leaderboardCache.data;
  }

  setLeaderboard(data: any[]): void {
    this.leaderboardCache = { data, timestamp: Date.now() };
  }

  clear(): void {
    this.replayCache.clear();
    this.matchListCache.clear();
    this.leaderboardCache = null;
  }
}

export const clientCache = new ClientCacheManager();
