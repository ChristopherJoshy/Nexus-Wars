export function Footer() {
  return (
    <footer className="border-t border-border mt-auto bg-card">
      <div className="max-w-6xl mx-auto px-4 h-12 flex items-center justify-between text-[11px] text-muted-foreground font-mono">
        <span className="tracking-wider">v1.0.0</span>
        <span>NEXUS WARS &copy; {new Date().getFullYear()}</span>
      </div>
    </footer>
  );
}
