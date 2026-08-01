import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import { TopBar } from "@/components/layout/TopBar";
import { CompetitionHeader } from "@/components/layout/CompetitionHeader";
import { CompetitionTabs } from "@/components/layout/CompetitionTabs";
import { TopLoader } from "@/components/layout/TopLoader";
import { AsciiLoader } from "@/components/layout/AsciiLoader";

export const metadata: Metadata = {
  title: "Nexus Wars — AI Bot Programming Competition",
  description:
    "Command orbital fleets in a 1v1 real-time strategy simulation. Conquer planets around a sun using ships and energy in continuous 2D space.",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32" },
      { url: "/icon.png", type: "image/png" },
    ],
    shortcut: "/favicon.ico",
    apple: "/icon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased max-w-full overflow-x-hidden" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          href="https://fonts.googleapis.com/css2?family=Caveat:wght@400;600;700&family=JetBrains+Mono:wght@400;500;700&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground font-sans max-w-full overflow-x-hidden">
        <Suspense fallback={null}>
          <TopLoader />
        </Suspense>
        <AsciiLoader />
        <div className="flex-1 flex flex-col min-w-0 max-w-full overflow-x-hidden">
          <TopBar />
          <CompetitionHeader />
          <CompetitionTabs />

          <main className="flex-1 max-w-[1700px] w-full mx-auto px-4 sm:px-6 py-5 overflow-x-hidden animate-in fade-in-50 duration-300">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
