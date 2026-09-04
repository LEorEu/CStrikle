import type { CSSProperties, ReactNode } from "react";
import { cn } from "../utils/cn";
import type { BoardCard, Position } from "../api/types";

export const POS_COLOR: Record<Position, string> = {
  IGL: "#ffc53d",
  AWPER: "#2fa8ff",
  RIFLER: "#8593a6",
};

/**
 * 标价和档位的关系。**这不是一个公式**——`grade` 和 `price` 都是后端给的,
 * 这里只是把两个数相减后换个说法(和 `/play` 那页的「抄底 / 买贵」同一套话术)。
 */
export type ValueTag = "STEAL" | "FAIR" | "OVERPAY";

export const valueTag = (grade: number, price: number): ValueTag =>
  grade > price ? "STEAL" : grade < price ? "OVERPAY" : "FAIR";

export const TAG_LABEL: Record<ValueTag, string> = {
  STEAL: "抄底",
  FAIR: "标价合理",
  OVERPAY: "买贵",
};

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

export function Tag({ children, color = "#ffc53d", className, dark }: { children: ReactNode; color?: string; className?: string; dark?: boolean }) {
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

/**
 * 盲选期的一张牌，选人页和首页那把扇形共用同一个牌面。
 *
 * 版式是从「价格标签 + 角色标签并排压在顶栏」改过来的：两个实心标签并排，
 * 谁都不让谁，斜切的多边形又给了它们一个没有来由的方向感，看着别扭。现在
 * **只有价格压在画面左上角**，角色退成一行有颜色的字排到下面——价格是买不买
 * 得起的门槛，先看它；角色和球探报告是"值不值"，那是下一层的事。
 *
 * 剪影按价位分两张：$1-$3 银边、$4-$5 金边。这不是额外信息（价格就印在同
 * 一张卡的左上角），只是让"这是张贵牌"在余光里也能成立。
 */
export function BlindCardFace({ card, highlight, compact, className, style, reveal, onDoubleClick, title }: {
  card: BoardCard; highlight?: boolean; compact?: boolean; className?: string; style?: CSSProperties;
  /** 翻开这张脸。**只有首页橱窗会传**——盲选期后端根本不发身份,传不进来。 */
  reveal?: { nickname: string; photo: string } | null;
  onDoubleClick?: () => void;
  title?: string;
}) {
  return (
    <div
      style={style}
      onDoubleClick={onDoubleClick}
      title={title}
      className={cn(
        "flex flex-col overflow-hidden border bg-bc-panel",
        highlight ? "border-bc-accent" : "border-bc-line",
        className,
      )}
    >
      <div className="relative aspect-[4/5] overflow-hidden bg-bc-bg">
        <img
          src={reveal?.photo ? `/img/${reveal.photo}` : `/img/silhouette/${card.price >= 4 ? "g" : "w"}.jpg`}
          alt=""
          className="h-full w-full object-cover object-top"
        />
        {/* 剪影底边收进面板色,免得图和下半张卡之间切出一条硬边 */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-bc-panel" />
        <PriceBadge price={card.price} size={compact ? "sm" : "md"} className="absolute left-0 top-0" />
        <span className={cn(
          "absolute inset-x-0 bottom-1 truncate px-1 text-center font-display font-black",
          reveal ? "text-bc-text drop-shadow-[0_2px_6px_rgba(0,0,0,0.9)]" : "text-bc-text/25",
          compact ? "text-xl" : "text-3xl",
        )}>{reveal ? reveal.nickname : "???"}</span>
      </div>
      <div className={cn("text-center", compact ? "px-1.5 pb-1.5" : "px-2.5 pb-2.5")}>
        <div className={cn("font-display font-black uppercase tracking-[0.2em]", compact ? "text-xs" : "text-sm")}
             style={{ color: POS_COLOR[card.position] }}>
          {card.position}
        </div>
        <div className="mt-0.5 flex items-center justify-center gap-1.5">
          {card.flag && <img src={`/img/${card.flag}`} alt="" className="h-2.5 w-auto" />}
          <span className={cn("truncate font-mono text-bc-muted", compact ? "text-[10px]" : "text-xs")}>{card.country}</span>
        </div>
        <div className={cn("mt-1.5 border border-bc-line/70 bg-bc-bg/40 text-left", compact ? "px-1.5 py-1" : "px-2 py-1.5")}>
          <div className="font-display text-[9px] font-bold uppercase tracking-[0.25em] text-bc-muted">球探报告</div>
          <div className={cn("font-display font-black leading-tight text-bc-accent", compact ? "text-sm" : "text-lg")}>
            {card.scout.label} {card.scout.lo}
            <span className="text-bc-muted">–</span>
            {card.scout.hi}
          </div>
          <div className={cn("truncate text-bc-muted", compact ? "text-[10px]" : "text-xs")}>· {card.clue}</div>
        </div>
      </div>
    </div>
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

export function StatBar({ label, value, color = "#ffc53d", compact }: { label: string; value: number; color?: string; compact?: boolean }) {
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

/**
 * 后端还没有的功能。**故意保留入口并写清楚「未实现」**——把屏藏掉会让人
 * 以为这块做完了,用前端逻辑补上则等于把玩法拆成两份实现。
 */
export function NotImplemented({ title, why, children }: { title: string; why: string; children?: ReactNode }) {
  return (
    <div className="relative overflow-hidden border border-dashed border-bc-muted/50 bg-bc-panel/50 p-5">
      <div className="pointer-events-none absolute inset-0 opacity-[0.06] [background:repeating-linear-gradient(45deg,#8593a6_0_10px,transparent_10px_20px)]" />
      <div className="relative">
        <div className="flex flex-wrap items-center gap-3">
          <span className="skew-tag bg-bc-muted px-2.5 py-0.5 font-display text-xs font-extrabold uppercase tracking-widest text-bc-bg">
            未实现
          </span>
          <span className="font-display text-xl font-black uppercase tracking-wider text-bc-muted">{title}</span>
        </div>
        <div className="mt-2 max-w-2xl text-sm text-bc-muted">{why}</div>
        {children && <div className="mt-3">{children}</div>}
      </div>
    </div>
  );
}

/**
 * 盲选卡上的通用剪影。**所有人共用同一个形状**——它不透露任何信息,身份要到
 * 揭晓那一屏才翻开。真实照片只出现在 `/api/run` 已经给出身份的地方。
 */
export function BlankFace({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 140" className={cn("h-full w-auto", className)} fill="currentColor" aria-hidden>
      <path d="M60 14c-15 0-25 11-25 28 0 11 4 21 11 27l-3 7c-10 4-33 12-33 29v35h100v-35c0-17-23-25-33-29l-3-7c7-6 11-16 11-27 0-17-10-28-25-28z" />
    </svg>
  );
}
