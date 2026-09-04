import { useEffect, useState } from "react";
import { fetchDraft } from "../api/client";
import type { BoardCard } from "../api/types";
import { BlankFace, Button, PosTag, PriceBadge } from "../components/ui";
import { cn } from "../utils/cn";

/**
 * 三步流程。原来这里是四张带说明的卡，右边整列都被它占着；现在那一列让给了
 * 真实牌面，剩下的只需要交代「往下会发生什么」，所以压成一行图标。
 *
 * 这里**不标**哪一步没做完——首页连着标四行「未实现」，进门先看见的是一张
 * 缺陷清单。缺什么由各屏自己的 `<NotImplemented>` 当场说（Build 的 Rogue
 * Shop、Tournament 的积分榜、Final 的淘汰赛），那是走到跟前才需要知道的事，
 * 也是 web/README.md 那条「不许把入口藏起来」真正落地的地方。
 */
const FLOW = [
  {
    cn: "选满 5 人",
    icon: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
        <path d="M16 5.4a3 3 0 0 1 0 5.9" />
        <path d="M18 14.6c1.9.9 3 2.6 3 5.4" />
      </>
    ),
  },
  {
    cn: "揭晓",
    icon: (
      <>
        <path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6Z" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
  },
  {
    cn: "Major 之路",
    icon: (
      <>
        <path d="M8 4h8v5a4 4 0 0 1-8 0V4Z" />
        <path d="M8 5.4H5a3 3 0 0 0 3 3" />
        <path d="M16 5.4h3a3 3 0 0 1-3 3" />
        <path d="M12 16v4M8.5 20h7" />
      </>
    ),
  },
];

export function Intro({ seed, busy, onStart }: { seed: number; busy: boolean; onStart: (seed: number) => void }) {
  const [value, setValue] = useState(String(seed));
  const parsed = Number.parseInt(value, 10);
  const ok = Number.isFinite(parsed) && parsed >= 0;

  // 首屏那把牌是**这个局号真正的第一个市场日**，不是摆拍的假卡:同一个 seed
  // 点进去看到的就是这五张。所以它跟着输入框走，「换一局」当场换一副牌。
  //
  // 数据仍然只从 /api/draft 来（动作为空 = 第一天），前端一张牌都不自己造——
  // 造假卡就等于在外壳里养第二份选手库，这个仓库刚为那件事付过一次代价。
  const [board, setBoard] = useState<BoardCard[] | null>(null);
  useEffect(() => {
    if (!ok) return;
    let alive = true;
    // 输入框里每敲一个数字都发一次请求没必要,等手停下来
    const t = setTimeout(() => {
      fetchDraft(parsed, [])
        .then((s) => alive && setBoard(s.board))
        // 预览失败不弹错:后端没起来的话,点「开始一局」会给出真正的报错,
        // 首屏这里安静地空着就行,不要在进门第一眼堆一个红框。
        .catch(() => alive && setBoard(null));
    }, 280);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [parsed, ok]);

  return (
    <div className="relative flex min-h-[calc(100vh-5.75rem)] items-center justify-center overflow-hidden py-8">
      <div className="bc-spot pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute inset-x-0 h-24 animate-scan bg-gradient-to-b from-transparent via-white/[0.03] to-transparent" />
      <div className="relative z-10 grid w-full max-w-7xl gap-12 px-6 lg:grid-cols-[1.05fr_1fr]">
        <div className="animate-rise">
          <div className="mb-4 flex items-center gap-3">
            <span className="h-4 w-1 bg-bc-accent" />
            <span className="font-display text-sm font-bold uppercase tracking-[0.35em] text-bc-muted">Road To Major · 新局准备</span>
          </div>
          <h1 className="bc-worn font-display text-[88px] font-black uppercase leading-[0.85] tracking-tight md:text-[120px]">
            Blind
            <br />
            <span className="text-bc-accent">Draft</span>
          </h1>
          <p className="mt-5 max-w-2xl text-xl leading-[1.7] text-bc-muted">
            $15 预算，7 轮市场日，签下 5 名真实职业选手。
            <br />
            每张匿名卡只公开价格、角色、国籍、一项球探报告和一条身份线索。
            <br />
            选满 5 人后揭晓身份，带着你的阵容踏上 Major 之路。
          </p>

          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Button onClick={() => ok && onStart(parsed)} disabled={!ok || busy} className="px-10 py-3 text-xl">
              {busy ? "连接中…" : "开始一局 ▶"}
            </Button>
            <label className="flex items-center gap-2 border border-bc-line bg-bc-panel px-3 py-2">
              <span className="font-display text-[11px] font-bold tracking-[0.25em] text-bc-muted">局号</span>
              <input
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="w-28 bg-transparent font-mono text-lg text-bc-accent outline-none"
              />
            </label>
            <Button variant="ghost" onClick={() => setValue(String(Math.floor(Math.random() * 1e6)))} className="px-4 py-2 text-sm">
              换一局
            </Button>
          </div>
        </div>

        <div className="flex flex-col justify-center gap-10">
          {board && <Fan board={board} />}
          <div className="flex items-center justify-center gap-3 sm:gap-5">
            {FLOW.map((f, i) => (
              <div key={f.cn} className="flex items-center gap-3 sm:gap-5">
                {i > 0 && <span className="font-display text-bc-line">——▸</span>}
                <div className="flex animate-rise flex-col items-center gap-2" style={{ animationDelay: `${420 + i * 90}ms` }}>
                  <span className="flex h-12 w-12 items-center justify-center rounded-full border border-bc-line bg-bc-panel/70">
                    <svg viewBox="0 0 24 24" className="h-5 w-5 text-bc-accent" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      {f.icon}
                    </svg>
                  </span>
                  <span className="font-display text-sm font-bold tracking-wide text-bc-muted">{f.cn}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** 五张牌摊开成一把。中间那张抬起来，纯粹是构图，跟牌好不好没关系。 */
function Fan({ board }: { board: BoardCard[] }) {
  return (
    <div className="flex items-center justify-center pt-4">
      {board.map((card, i) => {
        const off = i - (board.length - 1) / 2;
        const mid = Math.abs(off) < 0.01;
        return (
          // 摊开的角度放在外层,入场动画放在内层。`animate-rise` 的关键帧自己
          // 写了 transform,跟扇形摆位放在同一个元素上会把它整个盖掉——动画一
          // 结束(fill-mode: both)五张牌就回到一条直线上。
          <div
            key={card.index}
            className="-mx-1.5 w-[7.5rem]"
            style={{
              // 绕底边转,五张牌就像捏在手里摊开,而不是各转各的
              transformOrigin: "50% 100%",
              transform: `rotate(${off * 7}deg) translateY(${Math.abs(off) ** 1.35 * 12}px) scale(${mid ? 1.1 : 1})`,
              zIndex: mid ? 10 : 5 - Math.abs(off),
            }}
          >
            <div className="animate-rise" style={{ animationDelay: `${180 + i * 70}ms` }}>
              <FanCard card={card} highlight={mid} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FanCard({ card, highlight }: { card: BoardCard; highlight: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden border bg-bc-panel",
        highlight
          ? "border-bc-accent shadow-[0_0_0_1px_#ffc53d,0_24px_70px_-18px_rgba(255,180,0,0.55)]"
          : "border-bc-line shadow-[0_18px_50px_-24px_rgba(0,0,0,0.9)]",
      )}
    >
      <div className="flex items-center justify-between bg-bc-panel2 px-2 py-1.5">
        <PriceBadge price={card.price} size="sm" />
        <PosTag pos={card.position} />
      </div>
      <div className="relative flex aspect-[4/5] items-end justify-center overflow-hidden bg-gradient-to-b from-bc-panel2 to-bc-bg">
        <div className="bc-grid absolute inset-0 opacity-40" />
        {/* 所有人共用同一个剪影:它不透露任何信息，脸要到揭晓那一屏才出现 */}
        <BlankFace className="relative h-[86%] text-bc-line/70" />
        <span className="absolute font-display text-2xl font-black text-bc-muted/70">???</span>
        <div className="absolute inset-x-0 top-0 flex items-center gap-1.5 bg-bc-bg/70 px-1.5 py-1 backdrop-blur">
          {card.flag && <img src={`/img/${card.flag}`} alt="" className="h-2.5 w-auto" />}
          <span className="truncate font-mono text-[10px] text-bc-muted">{card.country}</span>
        </div>
      </div>
      <div className="border-t border-bc-line px-2 py-1.5">
        <div className="font-display text-[9px] font-bold uppercase tracking-[0.25em] text-bc-muted">{card.scout.label}</div>
        <div className="font-display text-base font-black leading-tight text-bc-accent">
          {card.scout.lo}
          <span className="text-bc-muted">–</span>
          {card.scout.hi}
        </div>
        <div className="truncate text-[11px] text-bc-muted">{card.clue}</div>
      </div>
    </div>
  );
}
