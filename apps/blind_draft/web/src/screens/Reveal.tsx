import { useMemo, useState } from "react";
import { LowerThird } from "../components/Broadcast";
import { Button, GradePips, Panel, PosTag, PriceBadge, StatBar, TAG_COLOR, ValueTagBadge } from "../components/ui";
import { POS_COLOR, fairPrice, valueDelta, valueTag } from "../game/engine";
import type { DraftCard, Player, SignedCard } from "../game/types";
import { cn } from "../utils/cn";

interface Props {
  signed: SignedCard[];
  boards: DraftCard[][];
  budget: number;
  onContinue: () => void;
}

export function Reveal({ signed, boards, budget, onContinue }: Props) {
  const [revealed, setRevealed] = useState(0);
  const [showMissed, setShowMissed] = useState(false);
  const allDone = revealed >= signed.length;

  const missed = useMemo(() => {
    const ids = new Set(signed.map((s) => s.id));
    return boards.flat().filter((c) => !ids.has(c.id));
  }, [boards, signed]);

  const summary = useMemo(() => {
    const withDelta = (cards: DraftCard[]) => cards.map((c) => ({ c, d: valueDelta(c.player, c.price) }));
    const mine = withDelta(signed);
    const miss = withDelta(missed);
    const bestSteal = [...mine].sort((a, b) => b.d - a.d || b.c.player.value - a.c.player.value)[0];
    const worstBuy = [...mine].sort((a, b) => a.d - b.d)[0];
    const biggestMiss = [...miss].sort((a, b) => b.d - a.d || b.c.player.value - a.c.player.value)[0];
    const dodged = [...miss].sort((a, b) => a.d - b.d)[0];
    return { bestSteal, worstBuy, biggestMiss, dodged };
  }, [signed, missed]);

  const totalSpent = signed.reduce((s, c) => s + c.price, 0);
  const totalFair = signed.reduce((s, c) => s + fairPrice(c.player.value), 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <LowerThird kicker="Reveal Segment" title={showMissed ? "The Ones That Got Away" : "Your Roster"} sub={showMissed ? "所有出现过但没被选中的卡" : `已揭晓 ${Math.min(revealed, signed.length)} / ${signed.length}`} color={showMissed ? "#ff2d3b" : "#ffb400"} />
        <div className="flex items-center gap-2">
          {!showMissed && !allDone && <Button onClick={() => setRevealed((r) => r + 1)}>Reveal Next ▶</Button>}
          {!showMissed && !allDone && (
            <Button variant="ghost" onClick={() => setRevealed(signed.length)}>
              Reveal All
            </Button>
          )}
          {!showMissed && allDone && <Button onClick={() => setShowMissed(true)}>Show Missed Cards ▶</Button>}
          {showMissed && <Button onClick={onContinue}>Go To Team Build ▶ (${budget})</Button>}
        </div>
      </div>

      {!showMissed && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {signed.map((card, i) => (
            <RevealCard key={card.id} card={card} revealed={i < revealed} />
          ))}
        </div>
      )}

      {!showMissed && allDone && (
        <Panel className="animate-rise p-4">
          <div className="grid gap-4 md:grid-cols-4">
            <Stat label="Total Spent" value={`$${totalSpent}`} />
            <Stat label="Fair Value" value={`$${totalFair}`} tone={totalFair > totalSpent ? "good" : totalFair < totalSpent ? "bad" : undefined} />
            <Stat label="Net" value={`${totalFair - totalSpent >= 0 ? "+" : ""}$${totalFair - totalSpent}`} tone={totalFair - totalSpent > 0 ? "good" : totalFair - totalSpent < 0 ? "bad" : undefined} />
            <Stat label="Carry Into Build" value={`$${budget}`} tone="good" />
          </div>
        </Panel>
      )}

      {showMissed && (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <Highlight kicker="Biggest Steal (Yours)" card={summary.bestSteal?.c} color="#2fe08a" />
            <Highlight kicker="Biggest Overpay (Yours)" card={summary.worstBuy?.c} color="#ff2d3b" />
            <Highlight kicker="Biggest Miss" card={summary.biggestMiss?.c} color="#ffb400" />
            <Highlight kicker="Bullet Dodged" card={summary.dodged?.c} color="#8593a6" />
          </div>
          <div className="space-y-3">
            {boards.map((board, r) => (
              <Panel key={r} title={`Round ${r + 1} Board`}>
                <div className="grid grid-cols-1 divide-y divide-bc-line md:grid-cols-5 md:divide-x md:divide-y-0">
                  {board.map((c) => {
                    const mine = signed.some((s) => s.id === c.id);
                    const tag = valueTag(c.player, c.price);
                    return (
                      <div key={c.id} className={cn("flex items-center gap-3 px-3 py-2.5", mine && "bg-bc-accent/10")}>
                        <PriceBadge price={c.price} size="sm" />
                        <div className="min-w-0 flex-1 leading-tight">
                          <div className="flex items-center gap-2">
                            <span className="truncate font-display text-lg font-black">{c.player.nick}</span>
                            <span className="text-sm">{c.player.flag}</span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] font-mono text-bc-muted">
                            <span style={{ color: POS_COLOR[c.player.position] }}>{c.player.position}</span>
                            <span>G{c.player.grade}</span>
                            <span>VAL {c.player.value}</span>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-display text-[10px] font-black uppercase tracking-widest" style={{ color: TAG_COLOR[tag] }}>
                            {tag}
                          </div>
                          {mine && <div className="font-display text-[10px] font-black uppercase tracking-widest text-bc-accent">Signed</div>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Panel>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div className="border-l-2 border-bc-line pl-3">
      <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">{label}</div>
      <div className={cn("font-display text-3xl font-black", tone === "good" && "text-bc-green", tone === "bad" && "text-bc-live")}>{value}</div>
    </div>
  );
}

function Highlight({ kicker, card, color }: { kicker: string; card?: DraftCard; color: string }) {
  if (!card) return null;
  return (
    <div className="flex animate-rise items-stretch border border-bc-line bg-bc-panel">
      <div className="w-1.5" style={{ background: color }} />
      <div className="flex-1 p-3">
        <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em]" style={{ color }}>
          {kicker}
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-display text-2xl font-black">{card.player.nick}</span>
          <span>{card.player.flag}</span>
        </div>
        <div className="font-mono text-[11px] text-bc-muted">
          R{card.round} · ${card.price} {card.player.position} · fair ${fairPrice(card.player.value)} · {card.clueText}
        </div>
      </div>
    </div>
  );
}

export function PlayerFace({ p, size = "md" }: { p: Player; size?: "sm" | "md" | "lg" }) {
  const dims = { sm: "h-10 w-10 text-base", md: "h-16 w-16 text-2xl", lg: "h-24 w-24 text-4xl" };
  return (
    <div
      className={cn("cut-corner flex shrink-0 items-center justify-center font-display font-black text-bc-bg", dims[size])}
      style={{ background: `linear-gradient(135deg, ${POS_COLOR[p.position]}, ${POS_COLOR[p.position]}88)` }}
    >
      {p.nick.slice(0, 2).toUpperCase()}
    </div>
  );
}

function RevealCard({ card, revealed }: { card: SignedCard; revealed: boolean }) {
  const p = card.player;
  const tag = valueTag(p, card.price);
  if (!revealed) {
    return (
      <div className="flex flex-col overflow-hidden border border-bc-line bg-bc-panel">
        <div className="flex items-center justify-between bg-bc-panel2 px-3 py-2">
          <PriceBadge price={card.price} />
          <PosTag pos={p.position} />
        </div>
        <div className="flex aspect-[4/5] items-center justify-center bg-gradient-to-b from-bc-panel to-bc-bg">
          <span className="font-display text-7xl font-black text-bc-line">?</span>
        </div>
        <div className="border-t border-bc-line px-3 py-2 text-sm text-bc-muted">{card.clueText}</div>
      </div>
    );
  }
  return (
    <div className="flex animate-flip flex-col overflow-hidden border bg-bc-panel" style={{ borderColor: TAG_COLOR[tag] }}>
      <div className="flex items-center justify-between bg-bc-panel2 px-3 py-2">
        <PriceBadge price={card.price} />
        <ValueTagBadge tag={tag} />
      </div>
      <div className="relative bg-gradient-to-b from-bc-panel2 to-bc-bg p-3">
        <div className="absolute right-2 top-2 font-display text-5xl font-black text-white/5">{card.clueText.replace(/^[^\w$]+/, "").slice(0, 3)}</div>
        <div className="flex items-center gap-3">
          <PlayerFace p={p} />
          <div className="min-w-0">
            <div className="truncate font-display text-2xl font-black leading-none">{p.nick}</div>
            <div className="mt-1 flex items-center gap-2 text-xs text-bc-muted">
              <span>{p.flag}</span>
              <span className="truncate">{p.club}</span>
              <span>·</span>
              <span>{p.age}</span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <PosTag pos={p.position} />
              <GradePips grade={p.grade} />
            </div>
          </div>
        </div>
        <div className="mt-3 space-y-1.5">
          <StatBar label="FIRE" value={p.attrs.firepower} color="#ff8a2a" compact />
          <StatBar label="LEAD" value={p.attrs.leadership} color="#ffb400" compact />
          <StatBar label="EXP" value={p.attrs.experience} color="#2fa8ff" compact />
          <StatBar label="STAB" value={p.attrs.stability} color="#2fe08a" compact />
        </div>
        <div className="mt-3 flex items-center justify-between border-t border-bc-line pt-2 font-mono text-[11px] text-bc-muted">
          <span>
            Major ×{p.majors} · 🏆 ×{p.champs}
          </span>
          <span>
            VAL <span className="text-bc-text">{p.value}</span> · fair ${fairPrice(p.value)}
          </span>
        </div>
      </div>
    </div>
  );
}
