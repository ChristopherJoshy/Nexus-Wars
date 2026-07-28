"use client";

export function CompetitionHeader() {

  return (
    <div className="py-7 border-b border-border bg-card">
      <div className="max-w-[1700px] mx-auto px-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-5">
        <div className="space-y-2 max-w-3xl">


          <h1 className="nw-display text-4xl sm:text-5xl font-bold text-foreground tracking-tight">
            Nexus Wars
          </h1>

          <p className="text-sm text-muted-foreground leading-relaxed max-w-xl">
            A live bot arena for precise decisions, predictive flight paths, and hard-won territory.
          </p>
        </div>
      </div>
    </div>
  );
}
