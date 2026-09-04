import { useEffect, useMemo, useRef, useState } from "react";
import { LowerThird } from "../components/Broadcast";
import { Button, NotImplemented, Panel, PosTag } from "../components/ui";
import type { Leg, MapRow, RunResult } from "../api/types";
import { deriveMap, type DerivedStat } from "../game/playByPlay";
import { cn } from "../utils/cn";

interface Props {
  run: RunResult;
  teamName: string;
  onFinish: () => void;
}

/**
 * Major 屏。**整届比赛在进这一屏之前就已经打完了**——`/api/run` 一次性返回
 * 玩家走过的每一场、每一图、每个人的火力账本。这里做的是把它按顺序播出来。
 *
 * 所以「下一场会怎样」在前端是已知的,但没有任何东西是前端算的:点 Play 只
 * 改变显示到第几个回合。
 */
export function Tournament({ run, teamName, onFinish }: Props) {
  const [legIdx, setLegIdx] = useState(0);
  const [inMatch, setInMatch] = useState(false);
  const played = run.legs.slice(0, legIdx);
  const leg = run.legs[legIdx];
  const done = legIdx >= run.legs.length;

  if (inMatch && leg) {
    return (
      <MatchView
        leg={leg}
        seed={run.seed}
        legIndex={legIdx}
        teamName={teamName}
        onDone={() => {
          setInMatch(false);
          setLegIdx((i) => i + 1);
        }}
      />
    );
  }

  const wins = played.filter((l) => l.won).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <LowerThird
          kicker={`Major · Stage ${leg?.stage ?? run.stage}`}
          title={done ? (run.reached_playoffs ? "Playoffs 晋级" : "止步瑞士轮") : (leg?.label ?? "")}
          sub={done ? `${run.wins}-${run.losses}` : `${teamName} 当前 ${wins}-${played.length - wins}`}
          color={done ? (run.reached_playoffs ? "#2fe08a" : "#ff2d3b") : "#2fa8ff"}
        />
        {!done && <Button onClick={() => setInMatch(true)}>Go To Match ▶</Button>}
        {done && <Button onClick={onFinish}>Post-Match Show ▶</Button>}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {leg && (
            <Panel title="Up Next" right={<span className="font-mono text-xs text-bc-accent">BO{leg.bo}</span>}>
              <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 p-6">
                <TeamBlock name={teamName} tag="YOU" color="#2fa8ff" entry={run.entry} note={`Stage ${run.stage} · Entry #${run.entry_rank}`} align="right" />
                <div className="text-center">
                  <div className="font-display text-5xl font-black text-bc-line">VS</div>
                  <div className="mt-1 font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">
                    {leg.label.split("·").slice(-1)[0].trim()}
                  </div>
                </div>
                <TeamBlock
                  name={leg.opponent.name}
                  tag={leg.opponent.name.slice(0, 3).toUpperCase()}
                  color="#ff2d3b"
                  entry={leg.opponent.entry}
                  note={leg.opponent.vrs ? `VRS #${leg.opponent.vrs} · Stage ${leg.opponent.stage}` : `Stage ${leg.opponent.stage}`}
                />
              </div>
              <div className="border-t border-bc-line px-4 py-2 text-xs text-bc-muted">
                这里不给「赛前胜率」：胜率只能实测，不能从系数上算（设计稿 §13.3）。
                能给的是双方 Entry、对手的 VRS 名次和本届 Stage —— 硬不硬自己判断。
              </div>
            </Panel>
          )}

          <Panel title="Match History">
            {played.length === 0 && <div className="p-4 text-sm text-bc-muted">尚未开赛。</div>}
            <div className="divide-y divide-bc-line">
              {played.map((h, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-2.5">
                  <div className="w-52 truncate font-display text-xs font-bold uppercase tracking-[0.2em] text-bc-muted">{h.label}</div>
                  <div className={cn("skew-tag px-2 py-0.5 font-display text-xs font-black text-bc-bg", h.won ? "bg-bc-green" : "bg-bc-live")}>
                    {h.won ? "WIN" : "LOSS"}
                  </div>
                  <div className="font-display text-xl font-black">
                    {h.player_maps} <span className="text-bc-muted">:</span> {h.opponent_maps}
                  </div>
                  <div className="flex-1 truncate text-sm">
                    vs <span className="font-bold">{h.opponent.name}</span>
                  </div>
                  <div className="hidden gap-1 font-mono text-[11px] text-bc-muted md:flex">
                    {h.maps.map((m, j) => (
                      <span key={j} className={cn("border px-1.5", m.player_won ? "border-bc-green/50 text-bc-green" : "border-bc-live/50 text-bc-live")}>
                        {m.margin > 0 ? "+" : ""}
                        {m.margin.toFixed(1)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title="Stage 进度">
            <div className="divide-y divide-bc-line">
              {run.stages.map((s) => (
                <div key={s.stage} className="flex items-center gap-3 px-3 py-2">
                  <span className="font-display text-sm font-black">Stage {s.stage}</span>
                  <span className="flex-1 font-mono text-sm">
                    {s.wins}-{s.losses}
                  </span>
                  <span className={cn("font-display text-xs font-bold uppercase tracking-widest", s.advanced ? "text-bc-green" : "text-bc-live")}>
                    {s.advanced ? "晋级" : "出局"}
                  </span>
                </div>
              ))}
              {run.stages.length === 0 && <div className="p-3 text-sm text-bc-muted">还没打完一段。</div>}
            </div>
          </Panel>

          <NotImplemented
            title="Swiss 积分榜"
            why="后端跑的是完整的 32 队三段瑞士轮，但 /api/run 只返回玩家自己走过的路径，没有其他 31 支队的逐轮战绩。前端拿掷硬币凑一张榜出来会是纯假数据。"
          />
        </div>
      </div>
    </div>
  );
}

function TeamBlock({ name, tag, color, entry, note, align }: { name: string; tag: string; color: string; entry: number; note: string; align?: "right" }) {
  return (
    <div className={cn("flex items-center gap-4", align === "right" && "flex-row-reverse text-right")}>
      <div className="cut-corner flex h-16 w-16 items-center justify-center font-display text-xl font-black text-bc-bg" style={{ background: color }}>
        {tag}
      </div>
      <div className="min-w-0">
        <div className="truncate font-display text-2xl font-black uppercase leading-none">{name}</div>
        <div className="mt-1 font-mono text-xs text-bc-muted">
          ENTRY {entry.toFixed(1)} · {note}
        </div>
      </div>
    </div>
  );
}

// ================= MATCH VIEW =================

function MatchView({ leg, seed, legIndex, teamName, onDone }: { leg: Leg; seed: number; legIndex: number; teamName: string; onDone: () => void }) {
  const [mapIdx, setMapIdx] = useState(0);
  const [roundIdx, setRoundIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const feedRef = useRef<HTMLDivElement>(null);

  const map = leg.maps[mapIdx];
  // 演绎出来的流水。key 只用来起随机数,同一张图每次都是同一条流水。
  const shownMap = useMemo(() => deriveMap(map, seed + legIndex * 31 + 1), [map, seed, legIndex]);
  const rounds = shownMap.rounds.slice(0, roundIdx);
  const mapDone = roundIdx >= shownMap.rounds.length;
  const isLastMap = mapIdx === leg.maps.length - 1;

  useEffect(() => {
    if (!playing || mapDone) return;
    const id = setInterval(() => setRoundIdx((r) => Math.min(shownMap.rounds.length, r + 1)), 700 / speed);
    return () => clearInterval(id);
  }, [playing, mapDone, speed, shownMap.rounds.length]);

  useEffect(() => {
    if (mapDone) setPlaying(false);
  }, [mapDone]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [roundIdx]);

  const ps = rounds.length ? rounds[rounds.length - 1].playerScore : 0;
  const os = rounds.length ? rounds[rounds.length - 1].opponentScore : 0;
  const mapsWonPlayer = leg.maps.slice(0, mapIdx).filter((m) => m.player_won).length + (mapDone && map.player_won ? 1 : 0);
  const mapsWonOpp = leg.maps.slice(0, mapIdx).filter((m) => !m.player_won).length + (mapDone && !map.player_won ? 1 : 0);

  const progress = shownMap.rounds.length ? roundIdx / shownMap.rounds.length : 0;
  const live = (stats: DerivedStat[]) =>
    stats.map((s) => ({ ...s, kills: Math.round(s.kills * progress), deaths: Math.round(s.deaths * progress) }));

  return (
    <div className="space-y-3">
      <div className="relative overflow-hidden border border-bc-line bg-bc-panel">
        <div className="shine pointer-events-none absolute inset-0 opacity-40" />
        <div className="relative grid grid-cols-[1fr_auto_1fr] items-stretch">
          <div className="flex items-center justify-end gap-4 bg-gradient-to-l from-bc-home/25 to-transparent px-5 py-3">
            <div className="text-right">
              <div className="font-display text-3xl font-black uppercase leading-none">{teamName}</div>
              <div className="font-mono text-[11px] text-bc-muted">MAPS {mapsWonPlayer} · STRENGTH {map.player_strength.toFixed(1)}</div>
            </div>
            <div className="cut-corner flex h-14 w-14 items-center justify-center bg-bc-home font-display text-lg font-black text-bc-bg">YOU</div>
            <div className="font-display text-6xl font-black tabular-nums text-bc-home">{ps}</div>
          </div>
          <div className="flex flex-col items-center justify-center bg-bc-bg px-6">
            <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">
              Map {mapIdx + 1}/{leg.maps.length} · BO{leg.bo}
            </div>
            <div className="font-display text-2xl font-black uppercase text-bc-accent">
              {map.margin > 0 ? "+" : ""}
              {map.margin.toFixed(1)}
            </div>
            <div className="font-mono text-xs text-bc-muted">{mapDone ? "FINAL" : `ROUND ${Math.min(rounds.length + 1, shownMap.rounds.length)}`}</div>
          </div>
          <div className="flex items-center gap-4 bg-gradient-to-r from-bc-away/25 to-transparent px-5 py-3">
            <div className="font-display text-6xl font-black tabular-nums text-bc-away">{os}</div>
            <div className="cut-corner flex h-14 w-14 items-center justify-center bg-bc-away font-display text-lg font-black text-bc-bg">
              {leg.opponent.name.slice(0, 3).toUpperCase()}
            </div>
            <div className="min-w-0">
              <div className="truncate font-display text-3xl font-black uppercase leading-none">{leg.opponent.name}</div>
              <div className="font-mono text-[11px] text-bc-muted">MAPS {mapsWonOpp} · STRENGTH {map.opponent_strength.toFixed(1)}</div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-[3px] border-t border-bc-line bg-bc-bg px-3 py-2">
          {shownMap.rounds.map((r, i) => (
            <span
              key={i}
              className={cn(
                "h-3 flex-1 transition-all",
                i < roundIdx ? (r.playerWon ? "bg-bc-home" : "bg-bc-away") : "bg-bc-line/50",
                i === 12 && "ml-2",
              )}
            />
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {!mapDone && (
          <Button onClick={() => setPlaying((p) => !p)} className="px-5 py-2 text-sm">
            {playing ? "❚❚ Pause" : roundIdx === 0 ? "▶ Start Map" : "▶ Resume"}
          </Button>
        )}
        {!mapDone && (
          <Button variant="ghost" onClick={() => setRoundIdx(shownMap.rounds.length)} className="px-4 py-2 text-sm">
            Skip To Result
          </Button>
        )}
        {!mapDone && (
          <div className="ml-2 flex items-center border border-bc-line">
            {[1, 2, 4].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={cn("px-3 py-1.5 font-mono text-xs", speed === s ? "bg-bc-accent text-bc-bg" : "text-bc-muted hover:text-bc-text")}
              >
                {s}x
              </button>
            ))}
          </div>
        )}
        {mapDone && !isLastMap && (
          <Button
            onClick={() => {
              setMapIdx((i) => i + 1);
              setRoundIdx(0);
              setPlaying(true);
            }}
            className="px-5 py-2 text-sm"
          >
            Next Map ▶
          </Button>
        )}
        {mapDone && isLastMap && (
          <Button onClick={onDone} variant={leg.won ? "primary" : "danger"} className="px-5 py-2 text-sm">
            {leg.won ? "Victory · Continue ▶" : "Defeat · Continue ▶"}
          </Button>
        )}
        {mapDone && (
          <div
            className={cn(
              "ml-auto skew-tag animate-pop px-4 py-1 font-display text-lg font-black uppercase tracking-[0.25em] text-bc-bg",
              map.player_won ? "bg-bc-home" : "bg-bc-away",
            )}
          >
            {map.player_won ? teamName : leg.opponent.name} 拿下这张图
          </div>
        )}
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_380px]">
        <div className="grid gap-3 md:grid-cols-2">
          <ScoreTable title={teamName} color="#2fa8ff" stats={live(shownMap.playerStats)} />
          <ScoreTable title={leg.opponent.name} color="#ff2d3b" stats={live(shownMap.opponentStats)} />
        </div>
        <Panel title="Play-By-Play" right={<span className="font-mono text-[10px] text-bc-live">● 演绎</span>}>
          <div ref={feedRef} className="h-[340px] space-y-1.5 overflow-auto p-3 scrollbar-thin">
            {rounds.length === 0 && <div className="text-sm text-bc-muted">选手已就位，等待开局……</div>}
            {rounds.map((r) => (
              <div key={r.n} className="flex animate-rise items-start gap-2 text-sm">
                <span className={cn("mt-0.5 w-1.5 self-stretch", r.playerWon ? "bg-bc-home" : "bg-bc-away")} />
                <span className="w-16 shrink-0 font-mono text-xs text-bc-muted">
                  R{r.n} {r.playerScore}-{r.opponentScore}
                </span>
                <span className={cn(r.playerWon ? "text-bc-text" : "text-bc-muted")}>{r.event}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Ledger map={map} teamName={teamName} oppName={leg.opponent.name} />

      <div className="border border-dashed border-bc-muted/40 px-4 py-2 text-xs text-bc-muted">
        <span className="font-display font-bold uppercase tracking-[0.2em]">演绎</span> ——
        引擎只算到每图（谁赢、Margin、每人有效火力）。上面的回合流水和 K/D 是按这三样推出来的表演层：
        比分收敛到引擎给的结果，K/D 按 Carry 权重分，<span className="text-bc-text">不参与任何判定</span>。
        下面那张逐人账本才是引擎的原始输出。
      </div>
    </div>
  );
}

function ScoreTable({ title, color, stats }: { title: string; color: string; stats: DerivedStat[] }) {
  const sorted = [...stats].sort((a, b) => b.kills - a.kills);
  return (
    <Panel>
      <div className="flex items-center gap-2 border-b border-bc-line px-3 py-1.5">
        <span className="h-4 w-1" style={{ background: color }} />
        <span className="truncate font-display text-sm font-black uppercase tracking-wider">{title}</span>
      </div>
      <table className="w-full text-sm">
        <thead className="font-display text-[10px] uppercase tracking-[0.25em] text-bc-muted">
          <tr>
            <th className="px-3 py-1 text-left">Player</th>
            <th className="px-2 py-1 text-right">K</th>
            <th className="px-2 py-1 text-right">D</th>
            <th className="px-3 py-1 text-right">+/-</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {sorted.map((s) => {
            const diff = s.kills - s.deaths;
            return (
              <tr key={s.nickname} className="border-t border-bc-line/60">
                <td className="px-3 py-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-display text-base font-bold">{s.nickname}</span>
                    <PosTag pos={s.position as never} className="!text-[9px]" />
                  </div>
                </td>
                <td className="px-2 py-1.5 text-right">{s.kills}</td>
                <td className="px-2 py-1.5 text-right">{s.deaths}</td>
                <td className={cn("px-3 py-1.5 text-right", diff > 0 && "text-bc-green", diff < 0 && "text-bc-live")}>
                  {diff > 0 ? `+${diff}` : diff}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}

/** 引擎的原始输出:这张图每个人的火力怎么变的。**这一张表里没有一个数是前端算的。** */
function Ledger({ map, teamName, oppName }: { map: MapRow; teamName: string; oppName: string }) {
  return (
    <Panel title="逐人火力账本" right={<span className="font-mono text-[10px] text-bc-accent">引擎输出</span>}>
      <div className="grid gap-px bg-bc-line md:grid-cols-2">
        {[
          { name: teamName, rolls: map.players, fire: map.player_fire, tactical: map.player_tactical, structure: map.player_structure, choke: map.player_choke },
          { name: oppName, rolls: map.opponents, fire: map.opponent_fire, tactical: map.opponent_tactical, structure: map.opponent_structure, choke: map.opponent_choke },
        ].map((side) => (
          <div key={side.name} className="bg-bc-panel">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-bc-line px-3 py-2">
              <span className="truncate font-display text-sm font-black uppercase">{side.name}</span>
              <span className="font-mono text-[11px] text-bc-muted">火力聚合 {side.fire.toFixed(1)}</span>
              <span className="font-mono text-[11px] text-bc-muted">战术 {side.tactical.toFixed(2)}</span>
              <span className="font-mono text-[11px] text-bc-muted">结构 {side.structure.toFixed(1)}</span>
              <span className={cn("font-mono text-[11px]", side.choke > 0.05 ? "text-bc-live" : "text-bc-muted")}>
                压力 {side.choke > 0.05 ? `−${side.choke.toFixed(1)}` : "0.0"}
              </span>
            </div>
            <table className="w-full text-sm">
              <thead className="font-display text-[10px] uppercase tracking-[0.2em] text-bc-muted">
                <tr>
                  <th className="px-3 py-1 text-left">Player</th>
                  <th className="px-2 py-1 text-right">卡面</th>
                  <th className="px-2 py-1 text-right">本图</th>
                  <th className="px-2 py-1 text-right">状态</th>
                  <th className="px-2 py-1 text-right">压力</th>
                  <th className="px-3 py-1 text-right">软顶</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {side.rolls.map((r) => (
                  <tr key={r.nickname} className="border-t border-bc-line/60">
                    <td className="px-3 py-1.5">
                      <span className="font-display text-base font-bold">{r.nickname}</span>
                      <span className="ml-2 text-[10px] text-bc-muted">×{r.carry_weight.toFixed(2)}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right text-bc-muted">{r.base_firepower}</td>
                    <td className={cn("px-2 py-1.5 text-right font-bold", r.delta > 0 ? "text-bc-green" : r.delta < 0 ? "text-bc-live" : "")}>
                      {r.effective_firepower.toFixed(1)}
                    </td>
                    <td className="px-2 py-1.5 text-right text-bc-muted">{fmt(r.why.form)}</td>
                    <td className="px-2 py-1.5 text-right text-bc-muted">{fmt(r.why.pressure)}</td>
                    <td className="px-3 py-1.5 text-right text-bc-muted">{fmt(r.why.soft_capped)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-bc-line px-3 py-2 font-mono text-xs">
        <span>
          <span className="text-bc-muted">MVP</span> {map.mvp.nickname}（{map.mvp.effective_firepower.toFixed(1)}）
        </span>
        {map.life_game && (
          <span className="text-bc-green">
            LIFE GAME {map.life_game.nickname}（{fmt(map.life_game.delta)}）
          </span>
        )}
        {map.underperform && (
          <span className="text-bc-live">
            失常 {map.underperform.nickname}（{fmt(map.underperform.delta)}）
          </span>
        )}
        <span className="text-bc-muted">Map Residual {fmt(map.residual)}</span>
      </div>
    </Panel>
  );
}

const fmt = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(1);
