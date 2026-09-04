import { useEffect, useState } from "react";
import { BlindCardFace, Button, Panel, PosTag, PriceBadge, Tag } from "../components/ui";
import type { BoardCard, DraftState } from "../api/types";
import { cn } from "../utils/cn";

interface Props {
  state: DraftState;
  busy: boolean;
  onSign: (index: number) => void;
  onPass: () => void;
  onUndo?: () => void;
}

/**
 * 选人屏。**这里没有一行发牌逻辑**——板面、标价、球探区间、可不可以 Pass、
 * 本轮上限,全是 `/api/draft` 给的。点一张牌只是把它的下标 push 进动作序列。
 */
export function Draft({ state, busy, onSign, onPass, onUndo }: Props) {
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => setSelected(null), [state.turn, state.actions.length]);

  const sel = selected === null ? undefined : state.board[selected];

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <DayHeader state={state} />

        {/* 回溯挂在板面右上角,不在下面那块签约条里。它管的是「哪一天」,跟
            「签谁」是两件事——两个按钮并排的时候,回溯看起来像签约的一个选项。
            一直在(第一天灰着),不然板面会因为多出一颗按钮整体往下跳一格。 */}
        <div className="flex items-center justify-end">
          <Button
            variant="ghost"
            onClick={onUndo}
            disabled={!onUndo || busy}
            className="px-4 py-1.5 text-sm"
          >
            回溯一天
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {state.board.map((card, i) => (
            <BlindCard
              key={i}
              card={card}
              active={selected === card.index}
              onClick={() => setSelected(selected === card.index ? null : card.index)}
              delay={i * 70}
            />
          ))}
        </div>

        <Panel className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="min-h-[4.25rem] min-w-[240px] flex-1">
              {sel ? (
                <div className="animate-pop">
                  <div className="font-display text-[11px] font-bold uppercase tracking-[0.35em] text-bc-accent">待签</div>
                  <div className="font-display text-2xl font-black uppercase">
                    ${sel.price} {sel.position} <span className="text-bc-muted">·</span> {sel.clue}
                  </div>
                  <div className="text-sm text-bc-muted">
                    签下后剩余 ${state.left - sel.price}，还需 {state.slots_left - 1} 人。
                    {sel.scout.label}落在 {sel.scout.lo}–{sel.scout.hi} 之间 —— 这是球探报告，不是真值。
                  </div>
                </div>
              ) : (
                // 这里以前站着一段解释「买不起的牌不会发过来」的话。删掉了：那是
                // 玩两把就明白的事，而这块地方每一步都在眼前，不该被一句常驻说明占着。
                <div>
                  <div className="font-display text-[11px] font-bold uppercase tracking-[0.35em] text-bc-muted">球探台</div>
                  <div className="font-display text-2xl font-black text-bc-line">尚未选牌</div>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" disabled={!state.can_pass || busy} onClick={onPass}>
                跳过本轮
              </Button>
              {/* 钱在最前面:决定按不按这颗按钮的是价格,不是「签下」这两个字 */}
              <Button disabled={!sel || busy} onClick={() => sel && onSign(sel.index)}>
                {sel ? `$${sel.price} ` : ""}签下这名选手 ▶
              </Button>
            </div>
          </div>
        </Panel>
      </div>

      {/* 右列跟左边那块交易日头顶齐:左列的留白在 DayHeader 里，这里补上同样的
          一段，两列才在同一条线上起头。 */}
      <div className="space-y-4 pt-8">
        {/* 盲选期没有队名。队名是揭晓之后、看见自己签到了谁才起得出来的东西。 */}
        <Panel title="我的阵容" right={<span className="font-mono text-xs text-bc-muted">{state.owned.length}/{state.slots}</span>}>
          <div className="divide-y divide-bc-line">
            {Array.from({ length: state.slots }).map((_, i) => {
              const s = state.owned[i];
              return (
                <div key={i} className="flex items-center gap-3 px-3 py-2.5">
                  <div className="font-display text-xl font-black text-bc-line">{i + 1}</div>
                  {s ? (
                    <>
                      <PriceBadge price={s.price} size="sm" />
                      <div className="flex-1 leading-tight">
                        <div className="flex items-center gap-2">
                          <PosTag pos={s.position} />
                          <span className="font-mono text-[11px] text-bc-muted">{s.country}</span>
                        </div>
                        <div className="text-sm">{s.clue}</div>
                      </div>
                      <div className="font-display text-2xl font-black text-bc-line">???</div>
                    </>
                  ) : (
                    <div className="flex-1 font-display text-sm uppercase tracking-[0.3em] text-bc-line">Empty Slot</div>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>

        <SquadNeeds state={state} />

        {/* 「可以去追」变成「构筑机会」，句子变成计数：一列 `0/2` 扫一眼就知道
            差多少，五条并排也还整齐。

            每行长得一模一样——英文标签 + 一个计数，不再有的行跟一句中文、有的
            行跟一个数。那句话没丢，挂在 tooltip 上；`have`/`want` 是后端给的，
            不是从 note 里抠的。 */}
        <Panel title="构筑机会">
          <div className="space-y-2 p-3">
            {state.blueprints.length === 0 && <div className="text-xs text-bc-muted">这一局没有还够得着的阵容标签。</div>}
            {state.blueprints.map((b) => (
              <div key={b.tag} className="flex items-center gap-2" title={b.note}>
                <Tag color={b.done ? "#2fe08a" : "#8593a6"}>{b.tag}</Tag>
                <span className={cn("ml-auto font-mono text-sm font-bold", b.done ? "text-bc-green" : "text-bc-text")}>
                  {b.have}
                  <span className="text-bc-muted">/{b.want}</span>
                </span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Desk Notes">
          <div className="space-y-2 p-3 text-xs text-bc-muted">
            <p>
              <Tag color="#2fe08a">Tip</Tag> 球探区间只覆盖这个位置最值得看的那一维；其余三维完全看不到。
            </p>
            <p>线索是俱乐部 / Major 次数 / 年龄三选一，同一个人固定给同一条。</p>
            {/* 这里原来印着 `seed 438100 · 动作 []`。动作序列是调试用的——一局
                =(局号, 动作)，后端靠它重放，玩家不需要看自己按过哪几个下标。
                局号本身有用（重开同一局的唯一入口），但它一整局都不变，摆在
                这堆规则说明的末尾像个脚注；现在挂在顶栏右边。 */}
          </div>
        </Panel>
      </div>
    </div>
  );
}

/**
 * 「第几天 / 剩多少钱」两栏四行 + 底下七天的进度，摆在版面正中。
 *
 * 原来这里是一块左对齐的 `<LowerThird>`，它顶头那条竖黄杠正好落在顶栏 logo
 * 那条竖黄杠底下——两个不相干的东西挤在同一条竖线上。而这四个数是选人时唯一
 * 需要一直盯着的：第几天、还剩多少钱、签了几个、还能跳几次。所以摆中间。
 *
 * 预算也是从顶栏搬下来的。剩多少钱每签一次就变，而顶栏说的是「这是什么节目、
 * 走到第几屏」——一个每一步都在跳的数字待在那儿，眼睛得在版面对角线上来回跑。
 *
 * 七天的进度条跟着它走：条说的是「第几天」，和上面那行是同一件事，没有理由
 * 拆到板面另一头去。整块上下都留够空，别贴着顶栏和牌。
 */
function DayHeader({ state }: { state: DraftState }) {
  return (
    <div className="flex flex-col items-center gap-5 pb-3 pt-8">
      <div className="animate-rise flex items-stretch gap-8 border-y border-bc-line bg-bc-panel/70 px-10 py-3.5 backdrop-blur">
        <div>
          <div className="font-display text-3xl font-black leading-none">
            第 <span className="text-bc-accent">{state.turn}</span>
            <span className="text-bc-muted"> / {state.turns}</span> 个交易日
          </div>
          <div className="mt-2 text-sm text-bc-muted">
            已签 <span className="font-mono text-bc-text">{state.owned.length} / {state.slots}</span>
          </div>
        </div>
        <div className="w-px bg-bc-line" />
        <div>
          <div className="font-display text-3xl font-black leading-none">
            剩余{" "}
            <span className="text-bc-accent">
              <span className="text-xl opacity-70">$</span>
              {state.left}
            </span>
          </div>
          <div className="mt-2 text-sm text-bc-muted">
            {state.can_pass ? `可以跳过 ${state.passes_left} 个交易日` : "接下来每天都必须签人"}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {Array.from({ length: state.turns }).map((_, i) => (
          <span
            key={i}
            title={state.passed.includes(i + 1) ? `第 ${i + 1} 个交易日：跳过` : `第 ${i + 1} 个交易日`}
            className={cn(
              "h-1.5 w-12 transition-colors",
              state.passed.includes(i + 1)
                ? "bg-bc-muted/60"
                : i + 1 < state.turn
                  ? "bg-bc-accent/50"
                  : i + 1 === state.turn
                    ? "bg-bc-accent"
                    : "bg-bc-line",
            )}
          />
        ))}
      </div>
    </div>
  );
}

//: 缺这个位置要付出什么代价。只在真的缺的时候才把对应那一条拿出来。
const NEED_WHY: Record<string, string> = {
  IGL: "没有指挥，每张图都拿不到战术执行分",
  AWPER: "没有 AWP，纸面火力要扣分",
};

/**
 * 阵容需求。**两档，不是一档。**
 *
 * 缺位置这件事在第 1 天和第 6 天完全不是一回事：第 1 天你什么都缺，那是起点，
 * 不是错误。这块原来是一条红杠横在板面正上方，开局就亮着，读起来像「我已经
 * 做错了什么」——而天天亮的警告等于没有警告。
 *
 * 平时它只是灰的一张需求清单。只有**剩下的席位刚好不够补齐缺口**时才转红：
 * 那一刻位置不再是「可以慢慢等」，每一个空位都被占死了。这一档判断纯粹是显示
 * 层的说法（缺几个 vs 还剩几个席位，两个数都是后端给的），不参与任何结算。
 */
function SquadNeeds({ state }: { state: DraftState }) {
  const need = state.missing;
  const why = need.map((p) => NEED_WHY[p]).filter(Boolean).join("；");
  const forced = need.length > 0 && state.slots_left > 0 && need.length >= state.slots_left;

  if (forced)
    return (
      <Panel title="⚠ 阵容警告" className="border-bc-live">
        <div className="border-l-2 border-bc-live p-3">
          <div className="font-display text-lg font-black leading-tight text-bc-live">
            {state.slots_left === 1 && need.length === 1
              ? `最后一个席位必须补 ${need[0]}`
              : `只剩 ${state.slots_left} 个席位，${need.join(" 和 ")} 都还没有`}
          </div>
          <p className="mt-1.5 text-xs text-bc-muted">{why}。</p>
        </div>
      </Panel>
    );

  return (
    <Panel title="阵容需求">
      <div className="p-3">
        {need.length === 0 ? (
          <div className="font-display text-lg font-black text-bc-green">位置齐了</div>
        ) : (
          <>
            <div className="font-display text-lg font-black text-bc-text">{need.map((p) => `缺 ${p}`).join(" · ")}</div>
            <p className="mt-1.5 text-xs text-bc-muted">{why}。</p>
          </>
        )}
      </div>
    </Panel>
  );
}

function BlindCard({ card, active, onClick, delay }: { card: BoardCard; active: boolean; onClick: () => void; delay: number }) {
  return (
    <button
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "group relative flex animate-rise flex-col text-left transition-all",
        active
          ? "-translate-y-1 shadow-[0_0_0_2px_#ffc53d,0_20px_60px_-20px_rgba(255,180,0,0.5)]"
          : "hover:-translate-y-0.5",
      )}
    >
      <BlindCardFace card={card} highlight={active} className={cn(!active && "group-hover:border-bc-muted")} />
      <div className={cn("h-1 w-full", active ? "bg-bc-accent" : "bg-bc-line group-hover:bg-bc-muted")} />
    </button>
  );
}
