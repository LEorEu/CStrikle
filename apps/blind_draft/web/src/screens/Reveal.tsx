import { useMemo, useState } from "react";
import {
  BlankFace,
  BlindCardFace,
  Button,
  GradePips,
  POS_COLOR,
  Panel,
  PosTag,
  PriceBadge,
  StatBar,
  TAG_COLOR,
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

  // 纸面火力强不强,两个后端给的数一起说:方向看跟全场平均比,「明显」看位次
  // 落在 32 队的哪一档。只用平均要自己定一个「差多少算明显」的门槛,只用位次
  // 又答不了差多少——两个都在手上,就都用上。
  const avg = run.entry_field_avg;
  const above = run.entry >= avg;
  const marked = above ? run.entry_rank <= 8 : run.entry_rank > 24;
  const fireWord = above ? (marked ? "明显高于" : "高于") : marked ? "明显低于" : "低于";
  const fireArrow = above ? (marked ? "↑↑" : "↑") : marked ? "↓↓" : "↓";

  // 缺哪个位置是后端算的(`missing`),这里只把它翻译成一句话
  const noIGL = draft.missing.includes("IGL");
  const noAWP = draft.missing.includes("AWPER");
  const squad = noIGL && noAWP ? "缺 IGL 和 AWP" : noIGL ? "缺少 IGL" : noAWP ? "缺少 AWP" : "角色完整";

  const done = Math.min(revealed, run.roster.length);

  return (
    <div className="space-y-5">
      {/* 页头跟选人屏同一个做法:居中、只放当下真正在动的那个数。
          原来这里是「Reveal Segment / Your Roster」两行英文——顶栏导航已经在
          「揭晓」上亮着了,标题再说一遍没有新信息;真正在变的只有翻到第几张。
          底下五个格子一人一格,和选人屏那七个交易日是同一套语言。 */}
      <div className="flex flex-col items-center gap-4 pb-1 pt-8">
        <div className="animate-rise border-y border-bc-line bg-bc-panel/70 px-10 py-3.5 text-center backdrop-blur">
          <div className="font-display text-3xl font-black leading-none">
            {allDone ? (
              "五个人全翻开了"
            ) : (
              <>
                已揭晓 <span className="text-bc-accent">{done}</span>
                <span className="text-bc-muted"> / {run.roster.length}</span>
              </>
            )}
          </div>
          <div className="mt-2 text-sm text-bc-muted">
            {allDone ? "这就是 $" + spent + " 买到的阵容" : "盲选期你只看得见标价、位置和一条线索"}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {run.roster.map((c, i) => (
            <span key={c.page} className={cn("h-1.5 w-12 transition-colors", i < done ? "bg-bc-accent" : "bg-bc-line")} />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {pairs.map((p, i) => (
          <RevealCard key={p.card.page} card={p.card} blind={p.blind} revealed={i < revealed} />
        ))}
      </div>

      {allDone && (
        <Panel className="animate-rise p-4">
          {/* 四格答四个问题:钱花了多少、买贵还是买对了、这五把枪硬不硬、
              这支队缺不缺零件。每一格都是「一个数 + 一句话凭什么这么说」。 */}
          <div className="grid gap-4 md:grid-cols-4">
            <Stat label="剩余预算" value={`$${draft.left}`} sub={`$${draft.budget} 里花掉了 $${spent}`} />
            <Stat
              label="估值差"
              value={`${gap > 0 ? "+" : ""}${gap}`}
              mark={gap > 0 ? "抄底" : gap < 0 ? "买贵" : "打平"}
              tone={gap > 0 ? "good" : gap < 0 ? "bad" : undefined}
              sub="五个人的档位合计 − 标价合计"
            />
            <Stat
              label="纸面火力"
              value={run.entry.toFixed(1)}
              mark={fireArrow}
              tone={above ? "good" : "bad"}
              // 平均值和位次本身不写出来:它们是这句话的算法,不是这句话的内容。
              // 「明显高于平均」已经是玩家要的那个答案,再报两个数只是让人多读一遍。
              sub={`${fireWord}本届参赛队平均`}
            />
            <Stat
              label="阵容状态"
              value={squad}
              tone={draft.missing.length ? "bad" : "good"}
              sub={`IGL ${noIGL ? "—" : "✓"} · AWP ${noAWP ? "—" : "✓"}`}
            />
          </div>
        </Panel>
      )}

      {/* 按钮跟着牌走,放在最下面:这一屏的动作是「再翻一张」,眼睛在牌上,手
          就该在牌下面。翻完之后同一个位置换成下一屏的入口。 */}
      <div className="flex items-center justify-center gap-3">
        {!allDone && (
          <>
            <Button variant="ghost" onClick={() => setRevealed(run.roster.length)}>
              揭晓全部
            </Button>
            <Button onClick={() => setRevealed((r) => r + 1)}>揭晓下一个 ▶</Button>
          </>
        )}
        {allDone && <Button onClick={onContinue}>进入阵容构筑 ▶</Button>}
      </div>
    </div>
  );
}

/** 一格:标题、一个大数、旁边一个记号、下面一句凭什么。 */
function Stat({ label, value, mark, sub, tone }: {
  label: string;
  value: string;
  /** 大数旁边那个小记号:抄底 / ↑↑ 之类 */
  mark?: string;
  sub?: string;
  tone?: "good" | "bad";
}) {
  const toned = tone === "good" ? "text-bc-green" : tone === "bad" ? "text-bc-live" : undefined;
  return (
    <div className="border-l-2 border-bc-line pl-3">
      <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className={cn("font-display text-3xl font-black leading-tight", toned)}>{value}</span>
        {mark && <span className={cn("font-display text-base font-black", toned ?? "text-bc-muted")}>{mark}</span>}
      </div>
      {sub && <div className="mt-1 text-xs leading-snug text-bc-muted">{sub}</div>}
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

  // 还没翻的那张就是选人屏上那张牌,一模一样的牌面(`BlindCardFace`)。这里
  // 曾经另画了一份更简单的——价格和角色并排压在顶栏、底下只剩一行线索——于是
  // 「翻面」看起来像换了一张卡,而不是同一张牌翻过来。
  if (!revealed) return <BlindCardFace card={blind} />;

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
            {/* 「抄底 / 买贵」印在卡顶那个色块上,这里只留它凭什么这么说 */}
            <span style={{ color: TAG_COLOR[tag] }}>
              档位 G{card.grade} / 标价 ${blind.price}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
