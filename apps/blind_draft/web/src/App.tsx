import { useCallback, useEffect, useMemo, useState } from "react";
import { PASS, fetchDraft, fetchRun } from "./api/client";
import type { DraftState, RunResult } from "./api/types";
import { Frame, Ticker, TopBar, type Phase, type TickerItem } from "./components/Broadcast";
import { Build } from "./screens/Build";
import { Draft } from "./screens/Draft";
import { Final } from "./screens/Final";
import { Intro } from "./screens/Intro";
import { Reveal } from "./screens/Reveal";
import { Tournament } from "./screens/Tournament";

const TEAM_NAMES = ["Blind Faith", "Paper Tigers", "Draft Dodgers", "Fog of War", "Mystery Machine", "No Scouting", "Budget Kings"];

const TICKER_BASE: TickerItem[] = [
  { label: "赛事快讯", text: "BO3 不会给强队额外加成，但更多地图通常会让实力更稳定地兑现" },
  { label: "球探提示", text: "球探报告只提供区间——它能缩小范围，但不会直接告诉你答案" },
  { label: "赛场观察", text: "高经验选手不会平白变得更强，但在生死局里更不容易失常" },
  { label: "经理提示", text: "一套火力很强的阵容，也可能因为缺少指挥而付出代价" },
  { label: "规则说明", text: "预算要给后面每个空位留 $1，所以买不起的牌不会发到你面前" },
  { label: "赛制说明", text: "32 队三阶段瑞士轮，Stage 归属由区域 VRS 名额决定" },
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

  const ticker = useMemo<TickerItem[]>(() => {
    const items = [...TICKER_BASE];
    if (draft && phase === "draft")
      items.unshift({
        label: "本局",
        text: `${teamName} 第 ${draft.turn}/${draft.turns} 个市场日 · 剩余 $${draft.left} · 还要签 ${draft.slots_left} 人`,
      });
    if (run && phase !== "draft" && phase !== "intro")
      items.unshift({
        label: "球队",
        text: `${teamName} 队伍强度 ${run.entry.toFixed(1)} · 全场 Entry 第 ${run.entry_rank} · 从 Stage ${run.stage} 打起`,
      });
    if (run && phase === "final")
      items.unshift({
        label: "战报",
        text: `${teamName} 最终 ${run.wins}-${run.losses}：${run.reached_playoffs ? "进入 Playoffs" : "止步瑞士轮"}`,
      });
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
