import { useMemo, useState } from "react";
import { LowerThird } from "../components/Broadcast";
import {
  BlankFace,
  Button,
  GradePips,
  POS_COLOR,
  Panel,
  PosTag,
  PriceBadge,
  StatBar,
  TAG_COLOR,
  TAG_LABEL,
  ValueTagBadge,
  valueTag,
} from "../components/ui";
import type { BoardCard, DraftState, RosterCard, RunResult } from "../api/types";
import { cn } from "../utils/cn";

interface Props {
  draft: DraftState;
  run: RunResult;
  onContinue: () => void;
}

/**
 * 揭晓屏。两份数据在这里合上:盲选期看到的那张牌(`draft.owned`)和翻开后的
 * 真身(`run.roster`)。两个数组同序——后端 `pages` 是按签下顺序给的,
 * `player_run` 原样保持,`test_draft_api.py` 钉着这条。
 */
export function Reveal({ draft, run, onContinue }: Props) {
  const [revealed, setRevealed] = useState(0);
  const allDone = revealed >= run.roster.length;

  const pairs = useMemo(
    () => run.roster.map((card, i) => ({ card, blind: draft.owned[i] })),
    [run.roster, draft.owned],
  );

  const spent = draft.spent;
  const gap = pairs.reduce((s, p) => s + (p.card.grade - p.blind.price), 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <LowerThird
          kicker="Reveal Segment"
          title="Your Roster"
          sub={`已揭晓 ${Math.min(revealed, run.roster.length)} / ${run.roster.length}`}
        />
        <div className="flex items-center gap-2">
          {!allDone && <Button onClick={() => setRevealed((r) => r + 1)}>Reveal Next ▶</Button>}
          {!allDone && (
            <Button variant="ghost" onClick={() => setRevealed(run.roster.length)}>
              Reveal All
            </Button>
          )}
          {allDone && <Button onClick={onContinue}>Team Build ▶</Button>}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {pairs.map((p, i) => (
          <RevealCard key={p.card.page} card={p.card} blind={p.blind} revealed={i < revealed} />
        ))}
      </div>

      {allDone && (
        <Panel className="animate-rise p-4">
          <div className="grid gap-4 md:grid-cols-4">
            <Stat label="Total Spent" value={`$${spent}`} />
            <Stat label="档位 − 标价" value={`${gap >= 0 ? "+" : ""}${gap}`} tone={gap > 0 ? "good" : gap < 0 ? "bad" : undefined} />
            <Stat label="队伍强度 Entry" value={run.entry.toFixed(1)} tone="good" />
            <Stat label="全场 Entry 位次" value={`#${run.entry_rank} / 32`} />
          </div>
          <div className="mt-3 border-t border-bc-line pt-3 text-xs text-bc-muted">
            Entry 是<span className="text-bc-text">纯火力口径</span>（Carry 权重 + 磨合 + 无狙罚），
            和比赛真正读的是同一个数 —— 页面显示的就是引擎打的。
          </div>
        </Panel>
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

/**
 * 一张小头像。有照片就用照片,没有(卡库里 7 个人没有)退回位置色的缩写块。
 *
 * `object-top` 是必须的:证件照裁成正方形时,`object-center` 会把人脸切一半。
 */
export function PlayerFace({ card, size = "md" }: { card: RosterCard; size?: "sm" | "md" | "lg" }) {
  const dims = { sm: "h-10 w-10 text-base", md: "h-16 w-16 text-2xl", lg: "h-24 w-24 text-4xl" };
  const [broken, setBroken] = useState(false);
  if (card.photo && !broken) {
    return (
      <img
        src={`/img/${card.photo}`}
        alt={card.nickname}
        onError={() => setBroken(true)}
        className={cn("cut-corner shrink-0 bg-bc-panel2 object-cover object-top", dims[size])}
      />
    );
  }
  return (
    <div
      className={cn("cut-corner flex shrink-0 items-center justify-center font-display font-black text-bc-bg", dims[size])}
      style={{ background: `linear-gradient(135deg, ${POS_COLOR[card.position]}, ${POS_COLOR[card.position]}88)` }}
    >
      {card.nickname.slice(0, 2).toUpperCase()}
    </div>
  );
}

function RevealCard({ card, blind, revealed }: { card: RosterCard; blind: BoardCard; revealed: boolean }) {
  const tag = valueTag(card.grade, blind.price);

  if (!revealed) {
    return (
      <div className="flex flex-col overflow-hidden border border-bc-line bg-bc-panel">
        <div className="flex items-center justify-between bg-bc-panel2 px-3 py-2">
          <PriceBadge price={blind.price} />
          <PosTag pos={blind.position} />
        </div>
        <div className="flex aspect-[4/5] items-end justify-center overflow-hidden bg-gradient-to-b from-bc-panel2 to-bc-bg">
          <BlankFace className="h-[86%] text-bc-line/70" />
        </div>
        <div className="border-t border-bc-line px-3 py-2 text-sm text-bc-muted">{blind.clue}</div>
      </div>
    );
  }

  // 球探区间给对了没有:真值落在区间里的哪一段
  const truth = (card as unknown as Record<string, number>)[blind.scout.attr];
  const span = Math.max(1, blind.scout.hi - blind.scout.lo);
  const at = Math.min(100, Math.max(0, ((truth - blind.scout.lo) / span) * 100));

  return (
    <div className="flex animate-flip flex-col overflow-hidden border bg-bc-panel" style={{ borderColor: TAG_COLOR[tag] }}>
      <div className="flex items-center justify-between bg-bc-panel2 px-3 py-2">
        <PriceBadge price={blind.price} />
        <ValueTagBadge tag={tag} />
      </div>

      {/* 和盲选态同一块地方、同一个比例:翻面看起来才像是同一张牌翻过来 */}
      <div className="relative aspect-[4/5] overflow-hidden bg-gradient-to-b from-bc-panel2 to-bc-bg">
        {card.photo ? (
          <img src={`/img/${card.photo}`} alt={card.nickname} className="h-full w-full object-cover object-top" />
        ) : (
          <div className="flex h-full items-end justify-center">
            <BlankFace className="h-[86%] text-bc-line/70" />
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-bc-panel via-bc-panel/85 to-transparent px-3 pb-2 pt-8">
          <div className="flex items-center gap-2">
            {card.flag && <img src={`/img/${card.flag}`} alt="" className="h-3 w-auto" />}
            <span className="truncate font-display text-2xl font-black leading-none">{card.nickname}</span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <PosTag pos={card.position} />
            <GradePips grade={card.grade} />
          </div>
        </div>
      </div>

      <div className="relative bg-bc-panel p-3">
        <div className="mb-2 truncate font-mono text-[11px] text-bc-muted">
          {[card.team, card.age ? `${card.age} 岁` : null, card.country].filter(Boolean).join(" · ")}
        </div>

        <div className="space-y-1.5">
          <StatBar label="FIRE" value={card.firepower} color="#ff8a2a" compact />
          <StatBar label="LEAD" value={card.leadership} color="#ffc53d" compact />
          <StatBar label="EXP" value={card.experience} color="#2fa8ff" compact />
          <StatBar label="STAB" value={card.stability} color="#2fe08a" compact />
        </div>

        <div className="mt-3 border-t border-bc-line pt-2">
          <div className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-muted">
            球探报告 {blind.scout.label} {blind.scout.lo}–{blind.scout.hi}
          </div>
          <div className="relative mt-1 h-2 bg-bc-line/60">
            <div className="absolute inset-y-0 w-0.5 bg-bc-accent" style={{ left: `${at}%` }} />
          </div>
          <div className="mt-1 flex justify-between font-mono text-[11px] text-bc-muted">
            <span>真值 {truth}</span>
            <span style={{ color: TAG_COLOR[tag] }}>
              {TAG_LABEL[tag]} · G{card.grade} / ${blind.price}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
