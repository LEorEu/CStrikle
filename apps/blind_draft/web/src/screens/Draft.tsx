import { useState } from "react";
import { LowerThird } from "../components/Broadcast";
import { Button, Panel, PosTag, PriceBadge, Tag } from "../components/ui";
import { ROSTER_SIZE, ROUNDS, canAfford } from "../game/engine";
import type { DraftCard, SignedCard } from "../game/types";
import { cn } from "../utils/cn";

const CLUE_LABEL: Record<string, string> = {
  country: "Nationality",
  club: "Last Known Club",
  age: "Age",
  majors: "Major Appearances",
  champs: "Major Titles",
};

interface Props {
  boards: DraftCard[][];
  round: number; // 1-based
  budget: number;
  signed: SignedCard[];
  passUsed: boolean;
  onSign: (card: DraftCard) => void;
  onPass: () => void;
}

export function Draft({ boards, round, budget, signed, passUsed, onSign, onPass }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const board = boards[round - 1] ?? [];
  const remainingRounds = ROUNDS - round + 1;
  const needed = ROSTER_SIZE - signed.length;
  const mustSign = needed >= remainingRounds; // no room for pass
  const canPass = !passUsed && !mustSign;
  const sel = board.find((c) => c.id === selected);

  const confirm = () => {
    if (sel) {
      onSign(sel);
      setSelected(null);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <LowerThird kicker="Draft Board" title={`Round ${round} / ${ROUNDS}`} sub={`已签 ${signed.length}/${ROSTER_SIZE} · 还需 ${needed} 人 · ${passUsed ? "Pass 已用" : "可 Pass 1 次"}`} />
          <div className="flex items-center gap-2 text-xs font-mono text-bc-muted">
            {Array.from({ length: ROUNDS }).map((_, i) => (
              <span key={i} className={cn("h-2 w-8", i + 1 < round ? "bg-bc-accent/50" : i + 1 === round ? "bg-bc-accent" : "bg-bc-line")} />
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {board.map((card, i) => {
            const affordable = canAfford(card.price, budget, signed.length);
            const active = selected === card.id;
            return (
              <button
                key={card.id}
                disabled={!affordable}
                onClick={() => setSelected(active ? null : card.id)}
                style={{ animationDelay: `${i * 70}ms` }}
                className={cn(
                  "group relative flex animate-rise flex-col overflow-hidden border text-left transition-all",
                  active ? "border-bc-accent shadow-[0_0_0_2px_#ffb400,0_20px_60px_-20px_rgba(255,180,0,0.5)] -translate-y-1" : "border-bc-line hover:border-bc-muted hover:-translate-y-0.5",
                  !affordable && "cursor-not-allowed opacity-35 grayscale",
                )}
              >
                <div className="flex items-center justify-between bg-bc-panel2 px-3 py-2">
                  <PriceBadge price={card.price} />
                  <PosTag pos={card.player.position} />
                </div>
                <div className="relative flex aspect-[4/5] items-center justify-center bg-gradient-to-b from-bc-panel to-bc-bg">
                  <div className="absolute inset-0 opacity-40 bc-grid" />
                  <Silhouette />
                  <div className="absolute inset-x-0 bottom-0 flex items-center justify-center pb-3">
                    <span className="font-display text-6xl font-black text-bc-line/80">?</span>
                  </div>
                  {!affordable && (
                    <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 bg-bc-live/90 py-1 text-center font-display text-xs font-black uppercase tracking-[0.3em] text-white">
                      Budget Lock
                    </div>
                  )}
                </div>
                <div className="border-t border-bc-line bg-bc-panel px-3 py-2">
                  <div className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-muted">{CLUE_LABEL[card.clueType]}</div>
                  <div className="font-display text-lg font-bold leading-tight">{card.clueText}</div>
                </div>
                <div className={cn("h-1 w-full", active ? "bg-bc-accent" : "bg-bc-line group-hover:bg-bc-muted")} />
              </button>
            );
          })}
        </div>

        <Panel className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex-1 min-w-[240px]">
              {sel ? (
                <div className="animate-pop">
                  <div className="font-display text-[11px] font-bold uppercase tracking-[0.35em] text-bc-accent">Pending Signature</div>
                  <div className="font-display text-2xl font-black uppercase">
                    ${sel.price} {sel.player.position} <span className="text-bc-muted">·</span> {sel.clueText}
                  </div>
                  <div className="text-sm text-bc-muted">
                    签下后剩余 ${budget - sel.price}，还需 {needed - 1} 人。
                    {budget - sel.price - (needed - 1) > 0 && ` 预计可带 $${budget - sel.price - (needed - 1)} 进入构筑阶段。`}
                  </div>
                </div>
              ) : (
                <div>
                  <div className="font-display text-[11px] font-bold uppercase tracking-[0.35em] text-bc-muted">Analyst Desk</div>
                  <div className="text-sm text-bc-muted">
                    选择一张卡。灰掉的卡会导致预算死局（剩下每人至少 $1）。{mustSign && <span className="text-bc-live"> 本轮必须签人！</span>}
                  </div>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" disabled={!canPass} onClick={onPass}>
                Pass
              </Button>
              <Button disabled={!sel} onClick={confirm}>
                Sign ✍
              </Button>
            </div>
          </div>
        </Panel>
      </div>

      <div className="space-y-4">
        <Panel title="Roster" right={<span className="font-mono text-xs text-bc-muted">{signed.length}/{ROSTER_SIZE}</span>}>
          <div className="divide-y divide-bc-line">
            {Array.from({ length: ROSTER_SIZE }).map((_, i) => {
              const s = signed[i];
              return (
                <div key={i} className="flex items-center gap-3 px-3 py-2.5">
                  <div className="font-display text-xl font-black text-bc-line">{i + 1}</div>
                  {s ? (
                    <>
                      <PriceBadge price={s.price} size="sm" />
                      <div className="flex-1 leading-tight">
                        <div className="flex items-center gap-2">
                          <PosTag pos={s.player.position} />
                          <span className="font-display text-sm font-bold uppercase tracking-widest text-bc-muted">R{s.pickedRound}</span>
                        </div>
                        <div className="text-sm">{s.clueText}</div>
                      </div>
                      <div className="font-display text-2xl font-black text-bc-line">???</div>
                    </>
                  ) : (
                    <div className="flex-1 font-display text-sm uppercase tracking-[0.3em] text-bc-line">Empty Slot</div>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel title="Spend Tracker">
          <div className="p-3 space-y-2">
            <div className="flex justify-between font-mono text-sm">
              <span className="text-bc-muted">Spent</span>
              <span>${15 - budget}</span>
            </div>
            <div className="flex justify-between font-mono text-sm">
              <span className="text-bc-muted">Reserved (min $1/slot)</span>
              <span>${needed}</span>
            </div>
            <div className="flex justify-between font-mono text-sm">
              <span className="text-bc-muted">Free for Build</span>
              <span className="text-bc-green">${Math.max(0, budget - needed)}</span>
            </div>
            <div className="mt-2 flex h-2 overflow-hidden bg-bc-line">
              <div className="bg-bc-accent" style={{ width: `${((15 - budget) / 15) * 100}%` }} />
              <div className="bg-bc-muted" style={{ width: `${(needed / 15) * 100}%` }} />
              <div className="bg-bc-green" style={{ width: `${(Math.max(0, budget - needed) / 15) * 100}%` }} />
            </div>
          </div>
        </Panel>

        <Panel title="Desk Notes">
          <div className="space-y-2 p-3 text-xs text-bc-muted">
            <p>
              <Tag color="#2fe08a">Tip</Tag> 冠军数 ×0 几乎是死线索；俱乐部和 Major 次数通常信息量最大。
            </p>
            <p>IGL 市场上限 $3 —— 看到 $3 IGL 未必便宜，看到 $1 IGL 可能是淘宝。</p>
            <p>五个 $1 也是合法路线：$10 全砸进 Rogue Build。</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Silhouette() {
  return (
    <svg viewBox="0 0 120 140" className="h-3/4 w-auto text-bc-line/70" fill="currentColor">
      <circle cx="60" cy="42" r="26" />
      <path d="M10 140c0-34 22-56 50-56s50 22 50 56z" />
    </svg>
  );
}
