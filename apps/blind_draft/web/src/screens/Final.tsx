import { LowerThird } from "../components/Broadcast";
import { Button, NotImplemented, Panel, PosTag, PriceBadge, TAG_LABEL, ValueTagBadge, valueTag } from "../components/ui";
import type { DraftState, RunResult } from "../api/types";
import { PlayerFace } from "./Reveal";
import { cn } from "../utils/cn";

interface Props {
  draft: DraftState;
  run: RunResult;
  teamName: string;
  onRestart: () => void;
}

/**
 * 散场屏。**这里的每一个数都来自 `/api/run`**——包括每个人在这一届里的
 * 火力表现:把他每张图的 delta 加起来,就是「这张牌兑现了没有」。
 */
export function Final({ draft, run, teamName, onRestart }: Props) {
  const good = run.reached_playoffs;
  const maps = run.legs.flatMap((l) => l.maps);
  const mapsWon = maps.filter((m) => m.player_won).length;

  // 逐人:这一届打了几张图、平均有效火力、相对卡面的净变化。全部由后端的
  // 逐人账本加总而来,没有引入任何新口径。
  const perPlayer = run.roster.map((card, i) => {
    const rolls = maps.flatMap((m) => m.players.filter((r) => r.nickname === card.nickname));
    const n = rolls.length || 1;
    return {
      card,
      blind: draft.owned[i],
      maps: rolls.length,
      eff: rolls.reduce((s, r) => s + r.effective_firepower, 0) / n,
      delta: rolls.reduce((s, r) => s + r.delta, 0) / n,
      mvps: maps.filter((m) => m.mvp.side === "player" && m.mvp.nickname === card.nickname).length,
    };
  });
  const best = [...perPlayer].sort((a, b) => b.delta - a.delta)[0];
  const worst = [...perPlayer].sort((a, b) => a.delta - b.delta)[0];

  return (
    <div className="space-y-5">
      <div className={cn("relative overflow-hidden border p-8", good ? "border-bc-green bg-[radial-gradient(ellipse_at_top,rgba(47,224,138,0.18),transparent_60%)]" : "border-bc-line bg-bc-panel")}>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <LowerThird
              kicker="Post-Match Show"
              title={good ? "进入 Playoffs" : "止步瑞士轮"}
              sub={`${teamName} · ${run.wins}-${run.losses} · 地图 ${mapsWon}/${maps.length} · Entry ${run.entry.toFixed(1)}`}
              color={good ? "#2fe08a" : "#ff2d3b"}
            />
          </div>
          <Button onClick={onRestart}>Run It Back ▶</Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Panel title="Draft Recap" right={<span className="font-mono text-[10px] text-bc-accent">引擎输出</span>}>
          <div className="divide-y divide-bc-line">
            {perPlayer.map((p) => {
              const tag = valueTag(p.card.grade, p.blind.price);
              return (
                <div key={p.card.page} className="flex items-center gap-4 px-4 py-3">
                  <PriceBadge price={p.blind.price} size="sm" />
                  <PlayerFace card={p.card} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-display text-xl font-black">{p.card.nickname}</span>
                      <PosTag pos={p.card.position} />
                      {p.mvps > 0 && (
                        <span className="skew-tag bg-bc-accent px-2 font-display text-[10px] font-black text-bc-bg">MVP ×{p.mvps}</span>
                      )}
                    </div>
                    <div className="font-mono text-[11px] text-bc-muted">
                      当初只看到「{p.blind.clue}」和{p.blind.scout.label} {p.blind.scout.lo}–{p.blind.scout.hi} · {TAG_LABEL[tag]}
                    </div>
                  </div>
                  <div className="text-right font-mono text-sm">
                    <div>
                      {p.card.firepower} <span className="text-bc-muted">→</span> {p.eff.toFixed(1)}
                    </div>
                    <div className={cn("text-xs", p.delta >= 0 ? "text-bc-green" : "text-bc-live")}>
                      {p.delta >= 0 ? "+" : "−"}
                      {Math.abs(p.delta).toFixed(1)} / 图
                    </div>
                  </div>
                  <ValueTagBadge tag={tag} />
                </div>
              );
            })}
          </div>
          <div className="border-t border-bc-line px-4 py-2 text-xs text-bc-muted">
            右边那一列是<span className="text-bc-text">卡面火力 → 这一届的平均有效火力</span>：
            差额来自状态、压力和软顶，逐图明细在比赛屏那张账本里。
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="这一届">
            <div className="space-y-2 p-4 font-mono text-sm">
              <Row k="Entry" v={run.entry.toFixed(1)} />
              <Row k="全场 Entry 位次" v={`#${run.entry_rank} / 32`} />
              <Row k="从哪一段打起" v={`Stage ${run.stage}`} />
              <Row k="战绩" v={`${run.wins}-${run.losses}`} />
              <Row k="选手花费" v={`$${draft.spent}`} />
              <Row k="剩余预算" v={`$${draft.left}`} />
              <Row k="放掉的市场日" v={draft.passed.length ? draft.passed.join(", ") : "无"} />
              <Row k="seed" v={String(run.seed)} />
            </div>
          </Panel>

          {best && worst && best !== worst && (
            <Panel title="兑现与没兑现">
              <div className="space-y-3 p-4 text-sm">
                <div className="border-l-2 border-bc-green pl-3">
                  <div className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-green">打出来了</div>
                  <div className="font-display text-xl font-black">{best.card.nickname}</div>
                  <div className="font-mono text-xs text-bc-muted">
                    ${best.blind.price} · 卡面 {best.card.firepower} · 场均 {best.eff.toFixed(1)}
                  </div>
                </div>
                <div className="border-l-2 border-bc-live pl-3">
                  <div className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-live">没打出来</div>
                  <div className="font-display text-xl font-black">{worst.card.nickname}</div>
                  <div className="font-mono text-xs text-bc-muted">
                    ${worst.blind.price} · 卡面 {worst.card.firepower} · 场均 {worst.eff.toFixed(1)}
                  </div>
                </div>
              </div>
            </Panel>
          )}

          <Panel title="Results">
            <div className="divide-y divide-bc-line">
              {run.legs.map((h, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-2 text-sm">
                  <span className={cn("w-6 font-display font-black", h.won ? "text-bc-green" : "text-bc-live")}>{h.won ? "W" : "L"}</span>
                  <span className="flex-1 truncate text-bc-muted">{h.label}</span>
                  <span className="font-mono">
                    {h.player_maps}-{h.opponent_maps}
                  </span>
                  <span className="w-24 truncate text-right font-display text-xs font-bold">{h.opponent.name}</span>
                </div>
              ))}
            </div>
          </Panel>

          <NotImplemented
            title="后悔值 · 淘汰赛"
            why="「当初选另一张牌会怎样」的穷举复盘目前只在命令行的 reveal() 里，是打印逻辑，还没有结构化接口。淘汰赛后端进 Playoffs 即终止，也没有夺冠路径。"
          />
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-bc-muted">{k}</span>
      <span>{v}</span>
    </div>
  );
}
