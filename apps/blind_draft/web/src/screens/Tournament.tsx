import { useEffect, useMemo, useRef, useState } from "react";
import { LowerThird } from "../components/Broadcast";
import { Button, Panel, PosTag } from "../components/ui";
import { generateOpponents, shuffle, simulateMatch, teamRating } from "../game/engine";
import type { Buff, MapResult, MatchDef, MatchOutcome, OpponentTeam, Player, TeamStats } from "../game/types";
import { cn } from "../utils/cn";

export interface TournamentResult {
  placement: string;
  placementRank: number; // 1 champion ... 
  history: MatchOutcome[];
  swissRecord: string;
}

interface Props {
  roster: Player[];
  stats: TeamStats;
  buffs: Buff[];
  teamName: string;
  onFinish: (r: TournamentResult) => void;
}

interface OppState extends OpponentTeam {
  w: number;
  l: number;
}

type View = "lobby" | "match";

export function Tournament({ roster, stats, buffs, teamName, onFinish }: Props) {
  const [opps, setOpps] = useState<OppState[]>(() => generateOpponents(new Set(roster.map((p) => p.id))).map((o) => ({ ...o, w: 0, l: 0 })));
  const [wins, setWins] = useState(0);
  const [losses, setLosses] = useState(0);
  const [history, setHistory] = useState<MatchOutcome[]>([]);
  const [stage, setStage] = useState<"swiss" | "playoffs">("swiss");
  const [playoffRound, setPlayoffRound] = useState(0); // 0 QF, 1 SF, 2 Final
  const [view, setView] = useState<View>("lobby");
  const [current, setCurrent] = useState<MatchOutcome | null>(null);
  const [finished, setFinished] = useState<TournamentResult | null>(null);

  const home = useMemo(() => ({ roster, stats, name: teamName, buffs }), [roster, stats, teamName, buffs]);
  const faced = useMemo(() => new Set(history.map((h) => h.def.opponent.id)), [history]);

  const nextDef = useMemo<MatchDef | null>(() => {
    if (finished) return null;
    if (stage === "swiss") {
      const candidates = opps.filter((o) => !faced.has(o.id) && o.w === wins && o.l === losses);
      const fallback = opps.filter((o) => !faced.has(o.id) && o.w + o.l === wins + losses);
      const any = opps.filter((o) => !faced.has(o.id));
      const pool = candidates.length ? candidates : fallback.length ? fallback : any;
      const opponent = shuffle(pool)[0];
      const adv = wins === 2;
      const elim = losses === 2;
      return {
        id: `swiss-${wins}-${losses}`,
        stage: "Swiss Stage",
        label: `Swiss Round ${wins + losses + 1} · ${wins}-${losses}`,
        opponent,
        bo: adv || elim ? 3 : 1,
        elimination: elim,
        advancement: adv,
      };
    }
    const labels = ["Quarterfinal", "Semifinal", "Grand Final"];
    const pool = shuffle(opps.filter((o) => !faced.has(o.id))).sort((a, b) => b.rating - a.rating).slice(0, 4);
    const opponent = shuffle(pool)[0] ?? opps[0];
    return {
      id: `po-${playoffRound}`,
      stage: "Playoffs",
      label: labels[playoffRound],
      opponent,
      bo: playoffRound === 2 ? 5 : 3,
      elimination: true,
      advancement: true,
    };
  }, [stage, opps, faced, wins, losses, playoffRound, finished]);

  const startMatch = () => {
    if (!nextDef) return;
    const outcome = simulateMatch(nextDef, home);
    setCurrent(outcome);
    setView("match");
  };

  const concludeMatch = () => {
    if (!current) return;
    const won = current.won;
    const newHistory = [...history, current];
    setHistory(newHistory);
    // simulate other teams' swiss results
    setOpps((prev) =>
      prev.map((o) => {
        if (o.id === current.def.opponent.id) return { ...o, w: o.w + (won ? 0 : 1), l: o.l + (won ? 1 : 0) };
        if (stage !== "swiss" || o.w >= 3 || o.l >= 3) return o;
        const p = 0.35 + (o.rating - 66) / 60;
        return Math.random() < p ? { ...o, w: o.w + 1 } : { ...o, l: o.l + 1 };
      }),
    );
    if (stage === "swiss") {
      const w = wins + (won ? 1 : 0);
      const l = losses + (won ? 0 : 1);
      setWins(w);
      setLosses(l);
      if (l === 3) {
        setFinished({ placement: `Swiss Exit (${w}-3)`, placementRank: 9 + (3 - w), history: newHistory, swissRecord: `${w}-3` });
      } else if (w === 3) {
        setStage("playoffs");
      }
    } else {
      if (!won) {
        const places = ["Top 8", "Top 4", "Runner-Up"];
        setFinished({ placement: places[playoffRound], placementRank: [8, 4, 2][playoffRound], history: newHistory, swissRecord: `${wins}-${losses}` });
      } else if (playoffRound === 2) {
        setFinished({ placement: "Major Champion", placementRank: 1, history: newHistory, swissRecord: `${wins}-${losses}` });
      } else {
        setPlayoffRound(playoffRound + 1);
      }
    }
    setCurrent(null);
    setView("lobby");
  };

  if (view === "match" && current) {
    return <MatchView outcome={current} roster={roster} teamName={teamName} onDone={concludeMatch} />;
  }

  const rating = teamRating(stats);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <LowerThird
          kicker={stage === "swiss" ? "Major · Swiss Stage" : "Major · Playoffs"}
          title={finished ? finished.placement : nextDef?.label ?? ""}
          sub={stage === "swiss" ? `${teamName} 当前 ${wins}-${losses} · 3 胜晋级 / 3 负淘汰` : "单败淘汰 · BO3 / 决赛 BO5"}
          color={finished ? (finished.placementRank === 1 ? "#ffb400" : "#ff2d3b") : "#2fa8ff"}
        />
        {!finished && nextDef && <Button onClick={startMatch}>Go To Match ▶</Button>}
        {finished && <Button onClick={() => onFinish(finished)}>Post-Match Show ▶</Button>}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {nextDef && !finished && (
            <Panel title="Up Next" right={<span className="font-mono text-xs text-bc-accent">BO{nextDef.bo}</span>}>
              <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 p-6">
                <TeamBlock name={teamName} tag="YOU" color="#2fa8ff" rating={rating} record={`${wins}-${losses}`} align="right" />
                <div className="text-center">
                  <div className="font-display text-5xl font-black text-bc-line">VS</div>
                  <div className="mt-1 font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">
                    {nextDef.advancement && nextDef.elimination ? "Elimination" : nextDef.advancement ? "Advancement" : nextDef.elimination ? "Elimination" : "Swiss"}
                  </div>
                </div>
                <TeamBlock name={nextDef.opponent.name} tag={nextDef.opponent.tag} color={nextDef.opponent.color} rating={nextDef.opponent.rating} record={stage === "swiss" ? `${opps.find((o) => o.id === nextDef.opponent.id)?.w ?? 0}-${opps.find((o) => o.id === nextDef.opponent.id)?.l ?? 0}` : nextDef.opponent.region} />
              </div>
            </Panel>
          )}

          <Panel title="Match History">
            {history.length === 0 && <div className="p-4 text-sm text-bc-muted">尚未开赛。</div>}
            <div className="divide-y divide-bc-line">
              {history.map((h, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-2.5">
                  <div className="w-40 font-display text-xs font-bold uppercase tracking-[0.2em] text-bc-muted">{h.def.label}</div>
                  <div className={cn("skew-tag px-2 py-0.5 font-display text-xs font-black text-bc-bg", h.won ? "bg-bc-green" : "bg-bc-live")}>{h.won ? "WIN" : "LOSS"}</div>
                  <div className="font-display text-xl font-black">
                    {h.homeMaps} <span className="text-bc-muted">:</span> {h.awayMaps}
                  </div>
                  <div className="flex-1 truncate text-sm">
                    vs <span className="font-bold" style={{ color: h.def.opponent.color }}>{h.def.opponent.name}</span>
                  </div>
                  <div className="hidden gap-1 font-mono text-[11px] text-bc-muted md:flex">
                    {h.maps.map((m, j) => (
                      <span key={j} className={cn("border px-1.5", m.winner === "home" ? "border-bc-green/50 text-bc-green" : "border-bc-live/50 text-bc-live")}>
                        {m.map} {m.homeScore}-{m.awayScore}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <Panel title={stage === "swiss" ? "Swiss Standings" : "Playoff Field"}>
          <div className="max-h-[520px] divide-y divide-bc-line overflow-auto scrollbar-thin">
            {[{ id: "you", name: teamName, tag: "YOU", color: "#2fa8ff", rating, w: wins, l: losses } as OppState, ...opps]
              .sort((a, b) => b.w - a.w || a.l - b.l || b.rating - a.rating)
              .map((o) => (
                <div key={o.id} className={cn("flex items-center gap-3 px-3 py-2", o.id === "you" && "bg-bc-home/10")}>
                  <span className="h-6 w-1" style={{ background: o.color }} />
                  <span className="w-10 font-display text-sm font-black">{o.tag}</span>
                  <span className="flex-1 truncate text-sm">{o.name}</span>
                  <span className={cn("font-mono text-sm", o.w >= 3 && "text-bc-green", o.l >= 3 && "text-bc-live")}>
                    {o.w}-{o.l}
                  </span>
                </div>
              ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function TeamBlock({ name, tag, color, rating, record, align }: { name: string; tag: string; color: string; rating: number; record: string; align?: "right" }) {
  return (
    <div className={cn("flex items-center gap-4", align === "right" && "flex-row-reverse text-right")}>
      <div className="cut-corner flex h-16 w-16 items-center justify-center font-display text-xl font-black text-bc-bg" style={{ background: color }}>
        {tag}
      </div>
      <div>
        <div className="font-display text-2xl font-black uppercase leading-none">{name}</div>
        <div className="mt-1 font-mono text-xs text-bc-muted">
          RTG {rating.toFixed(1)} · {record}
        </div>
      </div>
    </div>
  );
}

// ================= MATCH VIEW =================
function MatchView({ outcome, roster, teamName, onDone }: { outcome: MatchOutcome; roster: Player[]; teamName: string; onDone: () => void }) {
  const [mapIdx, setMapIdx] = useState(0);
  const [roundIdx, setRoundIdx] = useState(0); // number of rounds shown
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const feedRef = useRef<HTMLDivElement>(null);
  const map = outcome.maps[mapIdx];
  const shown = map.rounds.slice(0, roundIdx);
  const mapDone = roundIdx >= map.rounds.length;
  const isLastMap = mapIdx === outcome.maps.length - 1;
  const opp = outcome.def.opponent;

  useEffect(() => {
    if (!playing || mapDone) return;
    const id = setInterval(() => setRoundIdx((r) => Math.min(map.rounds.length, r + 1)), 900 / speed);
    return () => clearInterval(id);
  }, [playing, mapDone, speed, map.rounds.length]);

  useEffect(() => {
    if (mapDone) setPlaying(false);
  }, [mapDone]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [roundIdx]);

  const hs = shown.length ? shown[shown.length - 1].homeScore : 0;
  const as = shown.length ? shown[shown.length - 1].awayScore : 0;
  const mapsWonHome = outcome.maps.slice(0, mapIdx).filter((m) => m.winner === "home").length + (mapDone && map.winner === "home" ? 1 : 0);
  const mapsWonAway = outcome.maps.slice(0, mapIdx).filter((m) => m.winner === "away").length + (mapDone && map.winner === "away" ? 1 : 0);

  // live player stats: scale final stats by progress (approximation for live feel)
  const progress = map.rounds.length ? roundIdx / map.rounds.length : 0;
  const liveStats = (stats: MapResult["homeStats"]) =>
    stats.map((s) => ({ ...s, kills: Math.round(s.kills * progress), deaths: Math.round(s.deaths * progress) }));

  const nextMap = () => {
    setMapIdx((i) => i + 1);
    setRoundIdx(0);
    setPlaying(true);
  };

  return (
    <div className="space-y-3">
      {/* Scoreboard overlay */}
      <div className="relative overflow-hidden border border-bc-line bg-bc-panel">
        <div className="absolute inset-0 shine pointer-events-none opacity-40" />
        <div className="relative grid grid-cols-[1fr_auto_1fr] items-stretch">
          <div className="flex items-center justify-end gap-4 bg-gradient-to-l from-bc-home/25 to-transparent px-5 py-3">
            <div className="text-right">
              <div className="font-display text-3xl font-black uppercase leading-none">{teamName}</div>
              <div className="font-mono text-[11px] text-bc-muted">
                MAPS {mapsWonHome} · {outcome.def.stage.toUpperCase()}
              </div>
            </div>
            <div className="cut-corner flex h-14 w-14 items-center justify-center bg-bc-home font-display text-lg font-black text-bc-bg">YOU</div>
            <div className="font-display text-6xl font-black tabular-nums text-bc-home">{hs}</div>
          </div>
          <div className="flex flex-col items-center justify-center bg-bc-bg px-6">
            <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">
              Map {mapIdx + 1}/{outcome.maps.length} · BO{outcome.def.bo}
            </div>
            <div className="font-display text-2xl font-black uppercase text-bc-accent">{map.map}</div>
            <div className="font-mono text-xs text-bc-muted">{mapDone ? "FINAL" : `ROUND ${Math.min(shown.length + 1, map.rounds.length)}`}</div>
          </div>
          <div className="flex items-center gap-4 bg-gradient-to-r from-bc-away/25 to-transparent px-5 py-3">
            <div className="font-display text-6xl font-black tabular-nums text-bc-away">{as}</div>
            <div className="cut-corner flex h-14 w-14 items-center justify-center font-display text-lg font-black text-bc-bg" style={{ background: opp.color }}>
              {opp.tag}
            </div>
            <div>
              <div className="font-display text-3xl font-black uppercase leading-none">{opp.name}</div>
              <div className="font-mono text-[11px] text-bc-muted">
                MAPS {mapsWonAway} · {opp.region}
              </div>
            </div>
          </div>
        </div>
        {/* round strip */}
        <div className="flex items-center gap-[3px] border-t border-bc-line bg-bc-bg px-3 py-2">
          {map.rounds.map((r, i) => (
            <span
              key={i}
              className={cn(
                "h-3 flex-1 transition-all",
                i < roundIdx ? (r.winner === "home" ? "bg-bc-home" : "bg-bc-away") : "bg-bc-line/50",
                i === 12 && "ml-2",
              )}
              title={`R${r.n} ${r.homeScore}-${r.awayScore}`}
            />
          ))}
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        {!mapDone && (
          <Button onClick={() => setPlaying((p) => !p)} className="px-5 py-2 text-sm">
            {playing ? "❚❚ Pause" : roundIdx === 0 ? "▶ Start Map" : "▶ Resume"}
          </Button>
        )}
        {!mapDone && (
          <Button variant="ghost" onClick={() => setRoundIdx(map.rounds.length)} className="px-4 py-2 text-sm">
            Skip To Result
          </Button>
        )}
        {!mapDone && (
          <div className="ml-2 flex items-center border border-bc-line">
            {[1, 2, 4].map((s) => (
              <button key={s} onClick={() => setSpeed(s)} className={cn("px-3 py-1.5 font-mono text-xs", speed === s ? "bg-bc-accent text-bc-bg" : "text-bc-muted hover:text-bc-text")}>
                {s}x
              </button>
            ))}
          </div>
        )}
        {mapDone && !isLastMap && (
          <Button onClick={nextMap} className="px-5 py-2 text-sm">
            Next Map: {outcome.maps[mapIdx + 1].map} ▶
          </Button>
        )}
        {mapDone && isLastMap && (
          <Button onClick={onDone} variant={outcome.won ? "primary" : "danger"} className="px-5 py-2 text-sm">
            {outcome.won ? "Victory · Continue ▶" : "Defeat · Continue ▶"}
          </Button>
        )}
        {mapDone && (
          <div className={cn("ml-auto skew-tag px-4 py-1 font-display text-lg font-black uppercase tracking-[0.25em] text-bc-bg animate-pop", map.winner === "home" ? "bg-bc-home" : "bg-bc-away")}>
            {map.winner === "home" ? teamName : opp.name} takes {map.map}
          </div>
        )}
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_380px]">
        <div className="grid gap-3 md:grid-cols-2">
          <ScoreTable title={teamName} color="#2fa8ff" stats={liveStats(map.homeStats)} roster={roster} />
          <ScoreTable title={opp.name} color={opp.color} stats={liveStats(map.awayStats)} />
        </div>
        <Panel title="Play-By-Play" right={<span className="font-mono text-[10px] text-bc-live">● ON AIR</span>}>
          <div ref={feedRef} className="h-[340px] space-y-1.5 overflow-auto p-3 scrollbar-thin">
            {shown.length === 0 && <div className="text-sm text-bc-muted">选手已就位，等待开局……</div>}
            {shown.map((r) => (
              <div key={r.n} className="flex animate-rise items-start gap-2 text-sm">
                <span className={cn("mt-0.5 w-1.5 self-stretch", r.winner === "home" ? "bg-bc-home" : "bg-bc-away")} />
                <span className="w-16 shrink-0 font-mono text-xs text-bc-muted">
                  R{r.n} {r.homeScore}-{r.awayScore}
                </span>
                <span className={cn(r.winner === "home" ? "text-bc-text" : "text-bc-muted")}>{r.event}</span>
              </div>
            ))}
            {mapDone && (
              <div className="mt-2 border-t border-bc-line pt-2 font-display text-sm font-black uppercase tracking-[0.25em] text-bc-accent">
                {map.map} 结束 · {map.homeScore}-{map.awayScore}
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function ScoreTable({ title, color, stats, roster }: { title: string; color: string; stats: MapResult["homeStats"]; roster?: Player[] }) {
  const sorted = [...stats].sort((a, b) => b.kills - a.kills);
  return (
    <Panel>
      <div className="flex items-center gap-2 border-b border-bc-line px-3 py-1.5">
        <span className="h-4 w-1" style={{ background: color }} />
        <span className="font-display text-sm font-black uppercase tracking-wider">{title}</span>
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
            const p = roster?.find((r) => r.id === s.id);
            const diff = s.kills - s.deaths;
            return (
              <tr key={s.id} className="border-t border-bc-line/60">
                <td className="px-3 py-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-display text-base font-bold">{s.nick}</span>
                    {p && <PosTag pos={p.position} className="!text-[9px]" />}
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
