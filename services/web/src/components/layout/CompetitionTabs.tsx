"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/", label: "Overview" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/team", label: "Team" },
  { href: "/submit", label: "Submissions" },
];

export function CompetitionTabs() {
  const pathname = usePathname();

  return (
    <div className="bg-card border-b border-border px-6 sticky top-12 z-20">
      <div className="max-w-[1700px] mx-auto flex items-center gap-1 overflow-x-auto py-1 scrollbar-none">
        {tabs.map((tab) => {
          const isActive =
            tab.href === "/"
              ? pathname === "/"
              : pathname.startsWith(tab.href);

          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`px-3.5 py-2 text-xs transition-all whitespace-nowrap border-b-2 ${
                isActive
                  ? "border-primary text-primary font-semibold"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
