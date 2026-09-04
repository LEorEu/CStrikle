import type { ReactNode } from "react";
import { cn } from "../utils/cn";
import type { Position, ValueTag } from "../game/types";
import { POS_COLOR } from "../game/engine";

export function Panel({ children, className, title, right }: { children: ReactNode; className?: string; title?: string; right?: ReactNode }) {
  return (
    <div className={cn("relative border border-bc-line bg-bc-panel/90 backdrop-blur", className)}>
      {title && (
        <div className="flex items-center justify-between border-b border-bc-line bg-bc-panel2 px-3 py-1.5">
          <div className="font-display text-sm font-bold uppercase tracking-[0.2em] text-bc-muted">{title}</div>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

export function Tag({ children, color = "#ffb400", className, dark }: { children: ReactNode; color?: string; className?: string; dark?: boolean }) {
  return (
    <span
      className={cn("skew-tag inline-block px-2.5 py-0.5 font-display text-xs font-extrabold uppercase tracking-widest", className)}
      style={{ background: color, color: dark ? "#07090d" : "#07090d" }}
    >
      {children}
    </span>
  );
}

export function PosTag({ pos, className }: { pos: Position; className?: string }) {
  return (
    <Tag color={POS_COLOR[pos]} className={className}>
      {pos}
    </Tag>
  );
}

export function PriceBadge({ price, className, size = "md" }: { price: number; className?: string; size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "text-lg px-2", md: "text-2xl px-3", lg: "text-4xl px-4" };
  return (
    <span className={cn("cut-corner inline-flex items-center bg-bc-accent font-display font-black leading-none text-bc-bg", sizes[size], className)}>
      <span className="text-[0.6em] opacity-70">$</span>
      {price}
    </span>
  );
}

export const TAG_COLOR: Record<ValueTag, string> = {
  STEAL: "#2fe08a",
  FAIR: "#8593a6",
  OVERPAY: "#ff2d3b",
};

export function ValueTagBadge({ tag }: { tag: ValueTag }) {
  return (
    <span
      className="skew-tag inline-block px-3 py-1 font-display text-sm font-black uppercase tracking-[0.25em] text-bc-bg"
      style={{ background: TAG_COLOR[tag] }}
    >
      {tag}
    </span>
  );
}

export function StatBar({ label, value, color = "#ffb400", compact }: { label: string; value: number; color?: string; compact?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2", compact ? "text-[11px]" : "text-xs")}>
      <div className={cn("font-display font-bold uppercase tracking-widest text-bc-muted", compact ? "w-8" : "w-24")}>{label}</div>
      <div className="relative h-2 flex-1 overflow-hidden bg-bc-line/60">
        <div className="absolute inset-y-0 left-0 transition-all duration-700" style={{ width: `${Math.min(100, value)}%`, background: color }} />
      </div>
      <div className="w-7 text-right font-mono font-bold" style={{ color }}>
        {Math.round(value)}
      </div>
    </div>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "danger";
  className?: string;
}) {
  const styles = {
    primary: "bg-bc-accent text-bc-bg hover:bg-yellow-300",
    ghost: "border border-bc-line bg-transparent text-bc-text hover:border-bc-accent hover:text-bc-accent",
    danger: "bg-bc-live text-white hover:bg-red-500",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "cut-corner px-6 py-2.5 font-display text-base font-extrabold uppercase tracking-[0.2em] transition-all",
        styles[variant],
        disabled && "cursor-not-allowed opacity-30 hover:bg-bc-accent",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function LiveDot() {
  return (
    <span className="inline-flex items-center gap-1.5 bg-bc-live px-2 py-0.5 font-display text-xs font-black tracking-[0.25em] text-white">
      <span className="h-1.5 w-1.5 animate-blink rounded-full bg-white" />
      LIVE
    </span>
  );
}

export function GradePips({ grade }: { grade: number }) {
  return (
    <span className="inline-flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={cn("h-1.5 w-3", i <= grade ? "bg-bc-accent" : "bg-bc-line")} />
      ))}
    </span>
  );
}
