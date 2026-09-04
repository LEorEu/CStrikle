import { useCallback, useEffect, useMemo, useState } from "react";
import { PASS, fetchDraft, fetchRun } from "./api/client";
import type { DraftState, RunResult } from "./api/types";
import { Frame, Ticker, TopBar, type Phase } from "./components/Broadcast";
import { Build } from "./screens/Build";
import { Draft } from "./screens/Draft";
import { Final } from "./screens/Final";
import { Intro } from "./screens/Intro";
import { Reveal } from "./screens/Reveal";
import { Tournament } from "./screens/Tournament";

const TEAM_NAMES = ["Blind Faith", "Paper Tigers", "Draft Dodgers", "Fog of War", "Mystery Machine", "No Scouting", "Budget Kings"];

const TICKER_BASE = [
  "Blind Draft 赛季开启：$15 预算，7 个市场日，签 5 人",
  "分析师：卡面只给一维球探区间，其余全靠线索认人",
  "规则提醒：预算要给后面每个空位留 $1，买不起的牌不会发到你面前",
  "赛制：32 队三段瑞士轮，Stage 归属由区域 VRS 名额决定",
  "解说席：Stability 决定的是波动，不是另一种 Firepower",
  "提示：同一个 seed 和命令行 python -m blinddraft.draft --seed N 是同一局",
];

/**
 * 前端状态机。**这里不存局面,只存「我提交过哪些动作」。**
 *
 * 一局盲选是 `(seed, actions)`,每次动作都把完整序列发回 `/api/draft` 重放。
 * 好处是刷新不丢局、能把一局用一条链接发给别人,也彻底断了「前端自己算一半」
 * 的可能——`draft` 和 `run` 两个对象里的每个数都是后端给的。
 */
export default function App() {
  const [phase, setPhase] = useState<Phase>("intro");
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 1e6));
  const [actions, setActions] = useState<number[]>([]);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [run, setRun] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [teamName, setTeamName] = useState(TEAM_NAMES[0]);

  const load = useCallback(async (nextSeed: number, nextActions: number[]) => {
    setBusy(true);
    setError(null);
    try {
      const state = await fetchDraft(nextSeed, nextActions);
      setDraft(state);
      setActions(state.actions);
      return state;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const start = async (nextSeed: number) => {
    setSeed(nextSeed);
    setRun(null);
    setTeamName(TEAM_NAMES[nextSeed % TEAM_NAMES.length]);
    const state = await load(nextSeed, []);
    if (state) setPhase("draft");
  };

  // 签满五人 -> 把 pages 交给引擎跑完一整届。揭晓要的完整卡面也从这一份来,
  // 不为「翻开身份」单开一个接口。
  useEffect(() => {
    if (!draft?.done || !draft.pages || run) return;
    let alive = true;
    setBusy(true);
    fetchRun(draft.pages, draft.seed)
      .then((r) => {
        if (!alive) return;
        setRun(r);
        setPhase("reveal");
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, [draft, run]);

  const act = (a: number) => load(seed, [...actions, a]);
  const undo = () => load(seed, actions.slice(0, -1));

  const ticker = useMemo(() => {
    const items = [...TICKER_BASE];
    if (draft && phase === "draft")
      items.unshift(`${teamName} 第 ${draft.turn}/${draft.turns} 个市场日 · 剩余 $${draft.left} · 还要签 ${draft.slots_left} 人`);
    if (run && phase !== "draft" && phase !== "intro")
      items.unshift(`${teamName} 队伍强度 ${run.entry.toFixed(1)} · 全场 Entry 第 ${run.entry_rank} · Stage ${run.stage}`);
    if (run && phase === "final")
      items.unshift(`${teamName} 最终 ${run.wins}-${run.losses}：${run.reached_playoffs ? "进入 Playoffs" : "止步瑞士轮"}`);
    return items;
  }, [phase, teamName, draft, run]);

  return (
    <div className="bc-vignette min-h-screen">
      <TopBar phase={phase} budget={draft?.left ?? 15} subtitle={phase === "intro" ? undefined : teamName} />
      <Frame>
        {error && (
          <div className="mb-4 border border-bc-live bg-bc-live/10 px-4 py-3">
            <div className="font-display text-sm font-black uppercase tracking-[0.25em] text-bc-live">后端说不行</div>
            <div className="mt-1 font-mono text-sm">{error}</div>
            <div className="mt-1 text-xs text-bc-muted">
              调参后台没起来的话：<span className="font-mono">uvicorn bdserver.main:app --port 8621</span>
            </div>
          </div>
        )}

        {phase === "intro" && <Intro seed={seed} busy={busy} onStart={start} />}
        {phase === "draft" && draft && (
          <Draft
            state={draft}
            busy={busy}
            teamName={teamName}
            onSign={(i) => act(i)}
            onPass={() => act(PASS)}
            onUndo={actions.length ? undo : undefined}
          />
        )}
        {phase === "reveal" && draft && run && (
          <Reveal draft={draft} run={run} onContinue={() => setPhase("build")} />
        )}
        {phase === "build" && draft && run && (
          <Build draft={draft} run={run} teamName={teamName} onContinue={() => setPhase("tournament")} />
        )}
        {phase === "tournament" && run && (
          <Tournament run={run} teamName={teamName} onFinish={() => setPhase("final")} />
        )}
        {phase === "final" && draft && run && (
          <Final draft={draft} run={run} teamName={teamName} onRestart={() => setPhase("intro")} />
        )}

        {busy && phase !== "intro" && (
          <div className="mt-4 font-display text-xs uppercase tracking-[0.35em] text-bc-muted">Working…</div>
        )}
      </Frame>
      <Ticker items={ticker} />
    </div>
  );
}
