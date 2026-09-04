import { useMemo, useState } from "react";
import { Frame, Ticker, TopBar, type Phase } from "./components/Broadcast";
import { BUDGET, ROSTER_SIZE, ROUNDS, deriveTraits, finalTeamStats, generateBoards, teamRating } from "./game/engine";
import type { Buff, DraftCard, SignedCard } from "./game/types";
import { Build } from "./screens/Build";
import { Draft } from "./screens/Draft";
import { Final } from "./screens/Final";
import { Intro } from "./screens/Intro";
import { Reveal } from "./screens/Reveal";
import { Tournament, type TournamentResult } from "./screens/Tournament";

const TEAM_NAMES = ["Blind Faith", "Paper Tigers", "Draft Dodgers", "Fog of War", "Mystery Machine", "No Scouting", "Budget Kings"];

const TICKER_BASE = [
  "Blind Draft 赛季开启：$15 预算，6 轮匿名卡，签 5 人",
  "分析师：IGL 市场上限 $3，别指望 $5 指挥",
  "传闻：某 G5 狙击手本周被市场低估至 $4",
  "规则提醒：每局可 Pass 1 轮，预算死局将被系统锁定",
  "Rogue Shop 上新：运动心理学家 $4，双周集训 $2",
  "VRS 更新：Major 瑞士轮 3 胜晋级 3 负淘汰",
  "解说席：Stability 决定的是波动，不是另一种 Firepower",
];

export default function App() {
  const [phase, setPhase] = useState<Phase>("intro");
  const [boards, setBoards] = useState<DraftCard[][]>([]);
  const [round, setRound] = useState(1);
  const [budget, setBudget] = useState(BUDGET);
  const [signed, setSigned] = useState<SignedCard[]>([]);
  const [passUsed, setPassUsed] = useState(false);
  const [buffs, setBuffs] = useState<Buff[]>([]);
  const [teamName] = useState(() => TEAM_NAMES[Math.floor(Math.random() * TEAM_NAMES.length)]);
  const [result, setResult] = useState<TournamentResult | null>(null);
  const [runKey, setRunKey] = useState(0);

  const roster = useMemo(() => signed.map((s) => s.player), [signed]);
  const traits = useMemo(() => deriveTraits(roster), [roster]);
  const stats = useMemo(() => finalTeamStats(roster, traits, buffs), [roster, traits, buffs]);
  const buffSpent = buffs.reduce((s, b) => s + b.cost, 0);

  const start = () => {
    setBoards(generateBoards());
    setRound(1);
    setBudget(BUDGET);
    setSigned([]);
    setPassUsed(false);
    setBuffs([]);
    setResult(null);
    setRunKey((k) => k + 1);
    setPhase("draft");
  };

  const advanceRound = (nextSigned: SignedCard[]) => {
    if (nextSigned.length >= ROSTER_SIZE || round >= ROUNDS) {
      setPhase("reveal");
    } else {
      setRound((r) => r + 1);
    }
  };

  const onSign = (card: DraftCard) => {
    const next = [...signed, { ...card, pickedRound: round }];
    setSigned(next);
    setBudget((b) => b - card.price);
    advanceRound(next);
  };

  const onPass = () => {
    setPassUsed(true);
    advanceRound(signed);
  };

  const toggleBuff = (b: Buff) => {
    setBuffs((prev) => (prev.some((x) => x.id === b.id) ? prev.filter((x) => x.id !== b.id) : [...prev, b]));
  };

  const ticker = useMemo(() => {
    const items = [...TICKER_BASE];
    if (phase === "draft") items.unshift(`${teamName} 正在进行第 ${round} 轮选秀 · 剩余预算 $${budget}`);
    if (phase === "build") items.unshift(`${teamName} 完成选秀 · 阵容触发 ${traits.length} 个 Trait`);
    if (phase === "tournament") items.unshift(`${teamName} 进入 Major · 队伍评级 ${teamRating(stats).toFixed(1)}`);
    if (phase === "final" && result) items.unshift(`${teamName} 最终成绩：${result.placement}`);
    return items;
  }, [phase, teamName, round, budget, traits.length, stats, result]);

  const displayBudget = phase === "build" || phase === "tournament" || phase === "final" ? budget - buffSpent : budget;

  return (
    <div className="bc-vignette min-h-screen">
      <TopBar phase={phase} budget={displayBudget} subtitle={phase === "intro" ? undefined : teamName} />
      <Frame>
        {phase === "intro" && <Intro onStart={start} />}
        {phase === "draft" && (
          <Draft key={`${runKey}-${round}`} boards={boards} round={round} budget={budget} signed={signed} passUsed={passUsed} onSign={onSign} onPass={onPass} />
        )}
        {phase === "reveal" && <Reveal signed={signed} boards={boards} budget={budget} onContinue={() => setPhase("build")} />}
        {phase === "build" && <Build roster={roster} budget={budget} buffs={buffs} onToggleBuff={toggleBuff} onContinue={() => setPhase("tournament")} />}
        {phase === "tournament" && (
          <Tournament
            key={runKey}
            roster={roster}
            stats={stats}
            buffs={buffs}
            teamName={teamName}
            onFinish={(r) => {
              setResult(r);
              setPhase("final");
            }}
          />
        )}
        {phase === "final" && result && <Final result={result} signed={signed} buffs={buffs} teamName={teamName} onRestart={start} />}
      </Frame>
      <Ticker items={ticker} />
    </div>
  );
}
