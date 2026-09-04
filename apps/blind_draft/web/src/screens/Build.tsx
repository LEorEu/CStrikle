import { LowerThird } from "../components/Broadcast";
import { Button, GradePips, NotImplemented, Panel, PosTag, StatBar } from "../components/ui";
import type { DraftState, RunResult } from "../api/types";
import { PlayerFace } from "./Reveal";

interface Props {
  draft: DraftState;
  run: RunResult;
  teamName: string;
  onContinue: () => void;
}

/**
 * 构筑屏。左边那半是真的(阵容、四维、Entry、这一届的入场结果),
 * 右边那半是 Rogue Buff 商店——**后端没有这套东西,所以明写未实现**。
 */
export function Build({ draft, run, teamName, onContinue }: Props) {
  const spent = draft.spent;
  const left = draft.left;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <LowerThird
          kicker="Team Build"
          title={teamName}
          sub={`队伍强度 ${run.entry.toFixed(1)} · 全场第 ${run.entry_rank} · 从 Stage ${run.stage} 打起`}
          color="#d946ef"
        />
        <Button onClick={onContinue}>进入 Major ▶</Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
        <Panel title="Starting Five">
          <div className="divide-y divide-bc-line">
            {run.roster.map((p, i) => (
              <div key={p.page} className="flex items-center gap-3 px-3 py-2.5">
                <PlayerFace card={p} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-display text-lg font-black leading-none">{p.nickname}</span>
                    <span className="font-mono text-[10px] text-bc-muted">${draft.owned[i].price}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <PosTag pos={p.position} />
                    <GradePips grade={p.grade} />
                  </div>
                </div>
                <div className="text-right font-mono text-[10px] leading-tight text-bc-muted">
                  <div>
                    F<span className="text-bc-text">{p.firepower}</span> L<span className="text-bc-text">{p.leadership}</span>
                  </div>
                  <div>
                    E<span className="text-bc-text">{p.experience}</span> S<span className="text-bc-text">{p.stability}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="border-t border-bc-line bg-bc-panel2 px-3 py-2 font-mono text-xs text-bc-muted">
            选手花掉 ${spent} · 剩余 ${left} · 阵容快照 {run.snapshot}
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="这支队的样子">
            <div className="grid gap-4 p-4 sm:grid-cols-2">
              <div>
                <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">Entry（纯火力口径）</div>
                <div className="font-display text-6xl font-black text-bc-accent">{run.entry.toFixed(1)}</div>
                <div className="mt-1 text-xs text-bc-muted">
                  32 支正赛队里排第 {run.entry_rank}。这就是比赛真正读的那个数，页面上没有第二份。
                </div>
              </div>
              <div className="space-y-2">
                <StatBar label="FIRE" value={avg(run, "firepower")} color="#ff8a2a" />
                <StatBar label="LEAD" value={avg(run, "leadership")} color="#ffc53d" />
                <StatBar label="EXP" value={avg(run, "experience")} color="#2fa8ff" />
                <StatBar label="STAB" value={avg(run, "stability")} color="#2fe08a" />
                <div className="pt-1 text-[11px] text-bc-muted">
                  四条是五个人的均值，只用来看形状 —— Entry 走的是 Carry 权重，不是平均。
                </div>
              </div>
            </div>
            <div className="border-t border-bc-line px-4 py-3 text-sm">
              {draft.missing.length === 0 ? (
                <span className="text-bc-green">位置齐全：有狙有指挥。</span>
              ) : (
                <span className="text-bc-live">
                  缺 {draft.missing.join(" / ")} —— {draft.missing.includes("AWPER") && "无狙已经从 Entry 里扣过分；"}
                  {draft.missing.includes("IGL") && "没有指挥，每张图都拿不到战术执行分。"}
                </span>
              )}
            </div>
          </Panel>

          <Panel title="入场：你挤掉了谁">
            <div className="p-4 text-sm">
              <div className="text-bc-muted">
                Stage 归属由区域 VRS 名额决定，你是按 Entry 位次插进去的，名额守恒 —— 所以一定有人被往下挤。
              </div>
              <div className="mt-3 space-y-1.5">
                {run.demoted.length === 0 && <div className="text-bc-muted">没有人被降段。</div>}
                {run.demoted.map((d) => (
                  <div key={d.team} className="flex items-center gap-3 font-mono text-xs">
                    <span className="w-40 truncate font-display text-sm font-bold">{d.team}</span>
                    <span className="text-bc-muted">
                      Stage {d.from_stage} → {d.to_stage}
                    </span>
                  </div>
                ))}
                {run.dropped && (
                  <div className="mt-2 border-l-2 border-bc-live pl-3 font-mono text-xs text-bc-live">
                    {run.dropped} 被挤出了这一届正赛
                  </div>
                )}
              </div>
            </div>
          </Panel>

          <NotImplemented
            title="Rogue Shop"
            why="剩余预算买道具（运动心理学家、双周集训之类）这套系统后端没有：比赛引擎里没有对应的修正项，前端自己加等于凭空造一份数值。要做得先在 blinddraft/ 里立住，那是设计工作。"
          >
            <div className="font-mono text-xs text-bc-muted">
              剩余的 ${left} 目前不进入比赛，也不折算成任何加成。
            </div>
          </NotImplemented>
        </div>
      </div>
    </div>
  );
}

const avg = (run: RunResult, key: "firepower" | "leadership" | "experience" | "stability") =>
  run.roster.reduce((s, p) => s + p[key], 0) / (run.roster.length || 1);
