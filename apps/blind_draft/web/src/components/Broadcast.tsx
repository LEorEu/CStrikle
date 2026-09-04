import type { ReactNode } from "react";
import { cn } from "../utils/cn";
import { LiveDot } from "./ui";

export type Phase = "intro" | "draft" | "reveal" | "build" | "tournament" | "final";

const PHASES: { id: Phase; label: string }[] = [
  { id: "draft", label: "Blind Draft" },
  { id: "reveal", label: "Reveal" },
  { id: "build", label: "Team Build" },
  { id: "tournament", label: "Major" },
  { id: "final", label: "Wrap-Up" },
];

export function TopBar({ phase, budget, subtitle, right }: { phase: Phase; budget: number; subtitle?: string; right?: ReactNode }) {
  return (
    <header className="relative z-20 border-b border-bc-line bg-gradient-to-r from-bc-panel via-bc-panel2 to-bc-panel">
      <div className="mx-auto flex max-w-[1500px] items-center gap-4 px-4 py-2">
        <div className="flex items-center gap-3">
          <div className="cut-corner flex h-9 w-9 items-center justify-center bg-bc-accent font-display text-lg font-black text-bc-bg">F</div>
          <div className="leading-none">
            <div className="font-display text-lg font-black uppercase tracking-wider">
              ROAD TO <span className="text-bc-accent">MAJOR</span>
            </div>
            <div className="font-display text-[10px] font-semibold uppercase tracking-[0.35em] text-bc-muted">Blind Draft Broadcast</div>
          </div>
        </div>

        <nav className="ml-6 hidden items-center gap-1 md:flex">
          {PHASES.map((p, i) => {
            const idx = PHASES.findIndex((x) => x.id === phase);
            const state = i < idx ? "done" : i === idx ? "active" : "todo";
            return (
              <div
                key={p.id}
                className={cn(
                  "skew-tag px-3 py-1 font-display text-xs font-bold uppercase tracking-[0.2em]",
                  state === "active" && "bg-bc-accent text-bc-bg",
                  state === "done" && "bg-bc-line text-bc-text",
                  state === "todo" && "bg-bc-panel text-bc-muted",
                )}
              >
                {p.label}
              </div>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          {subtitle && <div className="hidden font-display text-sm font-semibold uppercase tracking-[0.25em] text-bc-muted lg:block">{subtitle}</div>}
          {right}
          <div className="flex items-center gap-2 border border-bc-line bg-bc-bg px-3 py-1">
            <span className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-muted">Budget</span>
            <span className="font-display text-2xl font-black leading-none text-bc-accent">
              <span className="text-sm opacity-70">$</span>
              {budget}
            </span>
          </div>
          <LiveDot />
        </div>
      </div>
    </header>
  );
}

export function Ticker({ items }: { items: string[] }) {
  const text = items.join("     ◆     ");
  return (
    <footer className="fixed inset-x-0 bottom-0 z-20 flex h-9 items-stretch border-t border-bc-line bg-bc-panel">
      <div className="flex shrink-0 items-center bg-bc-live px-4 font-display text-sm font-black uppercase tracking-[0.3em] text-white">
        Breaking
      </div>
      <div className="relative flex-1 overflow-hidden">
        <div className="absolute inset-y-0 flex w-max animate-ticker items-center whitespace-nowrap font-display text-sm font-semibold uppercase tracking-wider text-bc-text">
          <span className="px-8">{text}</span>
          <span className="px-8">{text}</span>
        </div>
      </div>
      <div className="hidden shrink-0 items-center gap-3 border-l border-bc-line px-4 font-mono text-xs text-bc-muted sm:flex">
        <span>FCS2.TV</span>
        <span className="text-bc-accent">●</span>
        <span>{new Date().getFullYear()} SEASON</span>
      </div>
    </footer>
  );
}

export function LowerThird({ kicker, title, sub, color = "#ffb400", className }: { kicker: string; title: string; sub?: string; color?: string; className?: string }) {
  return (
    <div className={cn("inline-flex animate-rise items-stretch", className)}>
      <div className="w-2" style={{ background: color }} />
      <div className="bg-bc-panel/95 pl-4 pr-8 py-2 backdrop-blur">
        <div className="font-display text-[11px] font-bold uppercase tracking-[0.35em]" style={{ color }}>
          {kicker}
        </div>
        <div className="font-display text-3xl font-black uppercase leading-none tracking-wide">{title}</div>
        {sub && <div className="mt-0.5 text-sm text-bc-muted">{sub}</div>}
      </div>
    </div>
  );
}

export function Frame({ children, className }: { children: ReactNode; className?: string }) {
  return <main className={cn("bc-grid relative z-10 mx-auto w-full max-w-[1500px] px-4 pb-16 pt-4", className)}>{children}</main>;
}
