"use client";

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

export function TopLoader() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    // Wrap initial state trigger in timeout/rAF to prevent synchronous setState warning
    const startTimer = setTimeout(() => {
      setLoading(true);
      setProgress(30);
    }, 0);

    const timer1 = setTimeout(() => setProgress(70), 120);
    const timer2 = setTimeout(() => setProgress(100), 280);
    const timer3 = setTimeout(() => setLoading(false), 480);

    return () => {
      clearTimeout(startTimer);
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
    };
  }, [pathname, searchParams]);

  if (!loading && progress === 0) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 h-0.5 bg-transparent pointer-events-none">
      <div
        className="h-full bg-primary transition-all duration-300 ease-out shadow-[0_0_8px_rgba(217,119,6,0.6)]"
        style={{
          width: `${progress}%`,
          opacity: loading ? 1 : 0,
        }}
      />
    </div>
  );
}
