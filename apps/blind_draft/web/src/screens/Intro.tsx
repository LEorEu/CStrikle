import { useState } from "react";
import { Button } from "../components/ui";

/**
 * 四步流程。`partial` 标的是**这一步里后端还没有的部分**——文案说的是这个
 * 模式该有的样子，标记负责说清楚现在还差什么，两者不能只留一个：
 * 只有文案会承诺不存在的东西，只有标记又不知道缺在哪。
 */
const STEPS = [
  {
    n: "01",
    title: "盲选",
    desc: "每个市场日出现 5 张匿名卡。根据有限线索、价格和阵容需求做选择，在 7 轮内签下 5 名选手。",
  },
  {
    n: "02",
    title: "揭晓",
    desc: "翻开 5 名选手的身份与完整四维，看看你买到了谁——哪些是捡漏，哪些又买贵了。",
  },
  {
    n: "03",
    title: "阵容构筑",
    desc: "查看这支队的火力、指挥、经验、稳定与默契，发现阵容缺口，以及已经触发或可以继续追的构筑方向。",
    partial: "Rogue Buff 商店尚未实现",
  },
  {
    n: "04",
    title: "Major 之路",
    desc: "进入 32 队三阶段瑞士轮，经历 BO1、晋级局和高压生死局，一路冲击 Playoffs 与冠军。",
    partial: "淘汰赛与夺冠尚未实现，进 Playoffs 即终止",
  },
];

export function Intro({ seed, busy, onStart }: { seed: number; busy: boolean; onStart: (seed: number) => void }) {
  const [value, setValue] = useState(String(seed));
  const parsed = Number.parseInt(value, 10);
  const ok = Number.isFinite(parsed) && parsed >= 0;

  return (
    <div className="relative flex min-h-[calc(100vh-5.75rem)] items-center justify-center overflow-hidden py-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(255,180,0,0.16),transparent_55%)]" />
      <div className="pointer-events-none absolute inset-x-0 h-24 animate-scan bg-gradient-to-b from-transparent via-white/[0.03] to-transparent" />
      <div className="relative z-10 grid w-full max-w-7xl gap-12 px-6 lg:grid-cols-[1.35fr_1fr]">
        <div className="animate-rise">
          <div className="mb-4 flex items-center gap-3">
            <span className="h-4 w-1 bg-bc-accent" />
            <span className="font-display text-sm font-bold uppercase tracking-[0.35em] text-bc-muted">Road To Major · 新局准备</span>
          </div>
          <h1 className="font-display text-[88px] font-black uppercase leading-[0.85] tracking-tight md:text-[120px]">
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

        <div className="animate-rise space-y-2.5 [animation-delay:150ms]">
          {STEPS.map((s) => (
            <div key={s.n} className="flex gap-4 border border-bc-line bg-bc-panel/80 px-4 py-3.5 backdrop-blur">
              <div className="font-display text-4xl font-black leading-none text-bc-accent/70">{s.n}</div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-xl font-bold tracking-wide">{s.title}</span>
                  {s.partial && (
                    <span className="border border-bc-muted/50 px-1.5 py-0.5 font-display text-[10px] font-bold tracking-[0.15em] text-bc-muted">
                      部分未实现
                    </span>
                  )}
                </div>
                <div className="mt-1 text-base leading-[1.65] text-bc-muted">{s.desc}</div>
                {s.partial && <div className="mt-1.5 text-sm text-bc-muted/70">— {s.partial}</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
