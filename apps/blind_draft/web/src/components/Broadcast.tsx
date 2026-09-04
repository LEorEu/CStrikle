import type { ReactNode } from "react";
import { cn } from "../utils/cn";
import { LiveDot } from "./ui";

export type Phase = "intro" | "draft" | "reveal" | "build" | "tournament" | "final";

const PHASES: { id: Phase; cn: string }[] = [
  { id: "draft", cn: "盲选" },
  { id: "reveal", cn: "揭晓" },
  { id: "build", cn: "阵容构筑" },
  { id: "tournament", cn: "Major 之路" },
  { id: "final", cn: "复盘" },
];

export function TopBar({ phase, budget, subtitle, right }: { phase: Phase; budget: number; subtitle?: string; right?: ReactNode }) {
  // 预算只在选人时是活的信息(每签一个人就变);比赛真正开打之前也没什么可 LIVE 的。
  const showBudget = phase === "draft";
  const showLive = phase === "tournament";

  // 底色走竖向渐变:上亮下暗,像一条被顶光打到的实体横条。之前是横向的
  // (from-panel via-panel2 to-panel),中间比两端亮一档,而版面上没有任何东西
  // 解释那个居中的亮团——它既不跟居中的导航对齐,也不跟别的面板一致。
  return (
    <header className="relative z-20 border-b border-bc-line bg-gradient-to-b from-bc-panel2 to-bc-panel">
      <div className="relative mx-auto flex max-w-[1500px] items-center gap-4 px-4 py-2">
        <div className="flex items-center gap-3">
          <span className="h-9 w-1 bg-bc-accent" />
          <div className="leading-none">
            <div className="font-display text-lg font-black uppercase tracking-wider">
              Blind <span className="text-bc-accent">Draft</span>
            </div>
            <div className="font-display text-[10px] font-semibold uppercase tracking-[0.35em] text-bc-muted">Road to Major</div>
          </div>
        </div>

        {/* 绝对居中:两侧宽度会随阶段变(预算、LIVE、队名),用 ml-auto 撑的话
            导航会跟着左右漂 */}
        <nav className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-7 md:flex">
          {PHASES.map((p, i) => {
            const idx = PHASES.findIndex((x) => x.id === phase);
            const state = i < idx ? "done" : i === idx ? "active" : "todo";
            return (
              <div
                key={p.id}
                className={cn(
                  "relative py-1 font-display text-base font-bold transition-colors",
                  state === "active" && "text-bc-accent",
                  state === "done" && "text-bc-text",
                  state === "todo" && "text-bc-muted/60",
                )}
              >
                {p.cn}
                {state === "active" && <span className="absolute inset-x-0 -bottom-0.5 h-[2px] bg-bc-accent" />}
              </div>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          {subtitle && <div className="hidden font-display text-sm font-semibold uppercase tracking-[0.25em] text-bc-muted lg:block">{subtitle}</div>}
          {right}
          {showBudget && (
            <div className="flex items-center gap-2 border border-bc-line bg-bc-bg px-3 py-1">
              <span className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-muted">Budget</span>
              <span className="font-display text-2xl font-black leading-none text-bc-accent">
                <span className="text-sm opacity-70">$</span>
                {budget}
              </span>
            </div>
          )}
          {showLive && <LiveDot />}
        </div>
      </div>
    </header>
  );
}

/** 滚动条上的一条:左边一个来源标签,右边一句话。 */
export interface TickerItem {
  label: string;
  text: string;
}

export function Ticker({ items }: { items: TickerItem[] }) {
  const run = (key: string) => (
    <span key={key} className="flex items-center">
      {items.map((it, i) => (
        <span key={i} className="flex items-center whitespace-nowrap px-6">
          <span className="font-display text-sm font-bold tracking-wide text-bc-accent">{it.label}</span>
          <span className="tick-sep px-3">◆</span>
          <span className="text-sm text-bc-text">{it.text}</span>
        </span>
      ))}
    </span>
  );
  return (
    <footer className="fixed inset-x-0 bottom-0 z-20 flex h-9 items-stretch border-t border-bc-line bg-bc-panel">
      <div className="flex shrink-0 items-center bg-bc-live px-4 font-display text-sm font-black uppercase tracking-[0.3em] text-white">
        Breaking
      </div>
      <div className="relative flex-1 overflow-hidden">
        <div className="absolute inset-y-0 flex w-max animate-ticker items-center">
          {run("a")}
          {run("b")}
        </div>
      </div>
      <div className="hidden shrink-0 items-center gap-3 border-l border-bc-line px-4 font-mono text-xs text-bc-muted sm:flex">
        <span>BDCS2.TV</span>
        <span className="text-bc-accent">●</span>
        <span>{new Date().getFullYear()} SEASON</span>
      </div>
    </footer>
  );
}

export function LowerThird({ kicker, title, sub, color = "#ffc53d", className }: { kicker: string; title: string; sub?: string; color?: string; className?: string }) {
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
  return <main className={cn("bc-grid relative z-10 mx-auto w-full max-w-[1500px] px-4 pb-16", className)}>{children}</main>;
}
