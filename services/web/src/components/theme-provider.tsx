"use client";

import * as React from "react";

type ThemeProviderState = {
  theme: "light";
  setTheme: (theme: string) => void;
  resolvedTheme: "light";
};

const initialState: ThemeProviderState = {
  theme: "light",
  setTheme: () => null,
  resolvedTheme: "light",
};

const ThemeProviderContext =
  React.createContext<ThemeProviderState>(initialState);

export function ThemeProvider({
  children,
}: {
  children: React.ReactNode;
  defaultTheme?: string;
  storageKey?: string;
}) {
  return (
    <ThemeProviderContext.Provider value={initialState}>
      {children}
    </ThemeProviderContext.Provider>
  );
}

export const useTheme = () => {
  const context = React.useContext(ThemeProviderContext);
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
};
