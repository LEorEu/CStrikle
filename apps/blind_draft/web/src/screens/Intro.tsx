import { useState } from "react";
import { Button, LiveDot } from "../components/ui";

export function Intro({ seed, busy, onStart }: { seed: number; busy: boolean; onStart: (seed: number) => void }) {
  const [value, setValue] = useState(String(seed));
  const parsed = Number.parseInt(value, 10);
  const ok = Number.isFinite(parsed) && parsed >= 0;

  return (
    <div className="relative flex min-h-[calc(100vh-3.5rem)] items-center justify-center overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(255,180,0,0.16),transparent_55%)]" />
      <div className="pointer-events-none absolute inset-x-0 h-24 animate-scan bg-gradient-to-b from-transparent via-white/[0.03] to-transparent" />
      <div className="relative z-10 grid w-full max-w-6xl gap-10 px-6 lg:grid-cols-[1.3fr_1fr]">
        <div className="animate-rise">
          <div className="mb-4 flex items-center gap-3">
            <LiveDot />
            <span className="font-display text-sm font-bold uppercase tracking-[0.35em] text-bc-muted">Season Opener · Studio A</span>
          </div>
          <h1 className="font-display text-[88px] font-black uppercase leading-[0.85] tracking-tight md:text-[120px]">
            Blind
            <br />
            <span className="text-bc-accent">Draft</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg text-bc-muted">
            $15 预算、7 个市场日、签下 5 名真实职业选手。你只能看到标价、位置、国籍，
            一条球探区间和一条身份线索。签满之后这支队会去打一届真实的 Major。
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button onClick={() => ok && onStart(parsed)} disabled={!ok || busy} className="text-xl px-10 py-3">
              {busy ? "Connecting…" : "Go Live ▶"}
            </Button>
            <label className="flex items-center gap-2 border border-bc-line bg-bc-panel px-3 py-2">
              <span className="font-display text-[10px] font-bold uppercase tracking-[0.3em] text-bc-muted">Seed</span>
              <input
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="w-28 bg-transparent font-mono text-lg text-bc-accent outline-none"
              />
            </label>
            <Button variant="ghost" onClick={() => setValue(String(Math.floor(Math.random() * 1e6)))} className="px-4 py-2 text-sm">
              Reroll
            </Button>
          </div>
        </div>

        <div className="animate-rise space-y-3 [animation-delay:150ms]">
          {[
            ["01", "Blind Draft", "每个市场日 5 张匿名卡。买不起的牌不会发到你面前，所以不存在预算死局。", true],
            ["02", "Reveal", "翻开身份、完整四维，以及这五张牌的档位和标价差在哪。", true],
            ["03", "Team Build", "看这支队的强度、缺口和构筑方向。Rogue Buff 商店尚未实现。", false],
            ["04", "Major", "32 队三段瑞士轮，逐图播报。进 Playoffs 即终止，淘汰赛尚未实现。", false],
          ].map(([n, t, d, full]) => (
            <div key={n as string} className="flex gap-4 border border-bc-line bg-bc-panel/80 p-4 backdrop-blur">
              <div className="font-display text-4xl font-black leading-none text-bc-accent/70">{n}</div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-display text-xl font-bold uppercase tracking-wider">{t}</span>
                  {!full && (
                    <span className="border border-bc-muted/50 px-1.5 py-0.5 font-display text-[9px] font-bold uppercase tracking-[0.2em] text-bc-muted">
                      部分未实现
                    </span>
                  )}
                </div>
                <div className="text-sm text-bc-muted">{d}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
