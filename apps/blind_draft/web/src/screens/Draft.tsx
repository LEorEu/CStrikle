import { useEffect, useState } from "react";
import { LowerThird } from "../components/Broadcast";
import { BlankFace, Button, Panel, PosTag, PriceBadge, Tag } from "../components/ui";
import type { BoardCard, DraftState } from "../api/types";
import { cn } from "../utils/cn";

interface Props {
  state: DraftState;
  busy: boolean;
  teamName: string;
  onSign: (index: number) => void;
  onPass: () => void;
  onUndo?: () => void;
}

/**
 * 选人屏。**这里没有一行发牌逻辑**——板面、标价、球探区间、可不可以 Pass、
 * 本轮上限,全是 `/api/draft` 给的。点一张牌只是把它的下标 push 进动作序列。
 */
export function Draft({ state, busy, teamName, onSign, onPass, onUndo }: Props) {
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => setSelected(null), [state.turn, state.actions.length]);

  const sel = selected === null ? undefined : state.board[selected];

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <LowerThird
            kicker="Draft Board"
            title={`Market Day ${state.turn} / ${state.turns}`}
            sub={`已签 ${state.owned.length}/${state.slots} · 还需 ${state.slots_left} 人 · ${
              state.can_pass ? `可以放掉 ${state.passes_left} 个市场日` : "接下来每天都必须签人"
            }`}
          />
          <div className="flex items-center gap-2 font-mono text-xs text-bc-muted">
            {Array.from({ length: state.turns }).map((_, i) => (
              <span
                key={i}
                className={cn(
                  "h-2 w-8",
                  state.passed.includes(i + 1)
                    ? "bg-bc-muted/60"
                    : i + 1 < state.turn
                      ? "bg-bc-accent/50"
                      : i + 1 === state.turn
                        ? "bg-bc-accent"
                        : "bg-bc-line",
                )}
              />
            ))}
          </div>
        </div>

        {state.missing.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-l-2 border-bc-live bg-bc-panel px-3 py-2 text-sm">
            <span className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-live">还缺</span>
            <span className="font-display text-lg font-black">{state.missing.join(" / ")}</span>
            <span className="text-bc-muted">缺 AWP 纸面火力要扣分，缺 IGL 每张图都拿不到战术执行分。</span>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {state.board.map((card, i) => (
            <BlindCard
              key={i}
              card={card}
              active={selected === card.index}
              onClick={() => setSelected(selected === card.index ? null : card.index)}
              delay={i * 70}
            />
          ))}
        </div>

        <Panel className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="min-w-[240px] flex-1">
              {sel ? (
                <div className="animate-pop">
                  <div className="font-display text-[11px] font-bold uppercase tracking-[0.35em] text-bc-accent">Pending Signature</div>
                  <div className="font-display text-2xl font-black uppercase">
                    ${sel.price} {sel.position} <span className="text-bc-muted">·</span> {sel.clue}
                  </div>
                  <div className="text-sm text-bc-muted">
                    签下后剩余 ${state.left - sel.price}，还需 {state.slots_left - 1} 人。
                    {sel.scout.label}落在 {sel.scout.lo}–{sel.scout.hi} 之间 —— 这是球探报告，不是真值。
                  </div>
                </div>
              ) : (
                <div>
                  <div className="font-display text-[11px] font-bold uppercase tracking-[0.35em] text-bc-muted">Analyst Desk</div>
                  <div className="text-sm text-bc-muted">
                    选一张卡。本轮标价上限 ${state.max_price} —— 买不起的牌后端根本不会发过来，所以板面上每一张都签得起。
                  </div>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              {onUndo && (
                <Button variant="ghost" onClick={onUndo} disabled={busy} className="px-4 py-2 text-sm">
                  ↩ Undo
                </Button>
              )}
              <Button variant="ghost" disabled={!state.can_pass || busy} onClick={onPass}>
                Pass
              </Button>
              <Button disabled={!sel || busy} onClick={() => sel && onSign(sel.index)}>
                Sign ✍
              </Button>
            </div>
          </div>
        </Panel>
      </div>

      <div className="space-y-4">
        <Panel title={teamName} right={<span className="font-mono text-xs text-bc-muted">{state.owned.length}/{state.slots}</span>}>
          <div className="divide-y divide-bc-line">
            {Array.from({ length: state.slots }).map((_, i) => {
              const s = state.owned[i];
              return (
                <div key={i} className="flex items-center gap-3 px-3 py-2.5">
                  <div className="font-display text-xl font-black text-bc-line">{i + 1}</div>
                  {s ? (
                    <>
                      <PriceBadge price={s.price} size="sm" />
                      <div className="flex-1 leading-tight">
                        <div className="flex items-center gap-2">
                          <PosTag pos={s.position} />
                          <span className="font-mono text-[11px] text-bc-muted">{s.country}</span>
                        </div>
                        <div className="text-sm">{s.clue}</div>
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

        <Panel title="可以去追">
          <div className="space-y-2 p-3">
            {state.blueprints.length === 0 && <div className="text-xs text-bc-muted">这一局没有还够得着的阵容标签。</div>}
            {state.blueprints.map((b) => (
              <div key={b.tag} className="flex items-center gap-2">
                <Tag color={b.done ? "#2fe08a" : "#8593a6"}>{b.tag}</Tag>
                <span className={cn("text-xs", b.done ? "text-bc-green" : "text-bc-muted")}>{b.note}</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Spend Tracker">
          <div className="space-y-2 p-3">
            <div className="flex justify-between font-mono text-sm">
              <span className="text-bc-muted">Spent</span>
              <span>${state.spent}</span>
            </div>
            <div className="flex justify-between font-mono text-sm">
              <span className="text-bc-muted">Reserved (min $1/slot)</span>
              <span>${state.slots_left}</span>
            </div>
            <div className="flex justify-between font-mono text-sm">
              <span className="text-bc-muted">本轮标价上限</span>
              <span className="text-bc-accent">${state.max_price}</span>
            </div>
            <div className="mt-2 flex h-2 overflow-hidden bg-bc-line">
              <div className="bg-bc-accent" style={{ width: `${(state.spent / state.budget) * 100}%` }} />
              <div className="bg-bc-muted" style={{ width: `${(state.slots_left / state.budget) * 100}%` }} />
              <div className="bg-bc-green" style={{ width: `${(Math.max(0, state.left - state.slots_left) / state.budget) * 100}%` }} />
            </div>
          </div>
        </Panel>

        <Panel title="Desk Notes">
          <div className="space-y-2 p-3 text-xs text-bc-muted">
            <p>
              <Tag color="#2fe08a">Tip</Tag> 球探区间只覆盖这个位置最值得看的那一维；其余三维完全看不到。
            </p>
            <p>线索是俱乐部 / Major 次数 / 年龄三选一，同一个人固定给同一条。</p>
            <p className="font-mono">seed {state.seed} · 动作 [{state.actions.join(", ")}]</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function BlindCard({ card, active, onClick, delay }: { card: BoardCard; active: boolean; onClick: () => void; delay: number }) {
  return (
    <button
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "group relative flex animate-rise flex-col overflow-hidden border text-left transition-all",
        active
          ? "-translate-y-1 border-bc-accent shadow-[0_0_0_2px_#ffc53d,0_20px_60px_-20px_rgba(255,180,0,0.5)]"
          : "border-bc-line hover:-translate-y-0.5 hover:border-bc-muted",
      )}
    >
      <div className="flex items-center justify-between bg-bc-panel2 px-3 py-2">
        <PriceBadge price={card.price} />
        <PosTag pos={card.position} />
      </div>
      <div className="relative flex aspect-[4/5] items-end justify-center overflow-hidden bg-gradient-to-b from-bc-panel2 to-bc-bg">
        <div className="bc-grid absolute inset-0 opacity-40" />
        {/* 所有人共用同一个剪影:它不透露任何信息，脸要到揭晓那一屏才出现 */}
        <BlankFace className="relative h-[86%] text-bc-line/70" />
        <div className="absolute inset-x-0 top-0 flex items-center gap-2 bg-bc-bg/70 px-2 py-1 backdrop-blur">
          {card.flag && <img src={`/img/${card.flag}`} alt="" className="h-3 w-auto" />}
          <span className="font-mono text-[11px] text-bc-muted">{card.country}</span>
        </div>
      </div>
      <div className="border-t border-bc-line bg-bc-panel px-3 py-2">
        <div className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-muted">{card.scout.label}</div>
        <div className="font-display text-xl font-black leading-tight text-bc-accent">
          {card.scout.lo}
          <span className="text-bc-muted">–</span>
          {card.scout.hi}
        </div>
        <div className="truncate text-sm text-bc-muted">{card.clue}</div>
      </div>
      <div className={cn("h-1 w-full", active ? "bg-bc-accent" : "bg-bc-line group-hover:bg-bc-muted")} />
    </button>
  );
}
