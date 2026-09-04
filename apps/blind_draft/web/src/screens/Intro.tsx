import { Button, LiveDot } from "../components/ui";
import { PLAYERS } from "../data/players";

export function Intro({ onStart }: { onStart: () => void }) {
  const counts = [1, 2, 3, 4, 5].map((g) => PLAYERS.filter((p) => p.grade === g).length);
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
            $15 预算、6 轮匿名卡、签下 5 名职业选手。你只能看到价格、位置和一条线索。
            揭晓之后，用剩下的钱构筑队伍，然后把这支队带进 Major。
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button onClick={onStart} className="text-xl px-10 py-3">
              Go Live ▶
            </Button>
            <div className="font-mono text-xs text-bc-muted">
              POOL {PLAYERS.length} CARDS · G5 {counts[4]} / G4 {counts[3]} / G3 {counts[2]} / G2 {counts[1]} / G1 {counts[0]}
            </div>
          </div>
        </div>

        <div className="animate-rise space-y-3 [animation-delay:150ms]">
          {[
            ["01", "Blind Draft", "每轮 5 张匿名卡：$5 / $4 / $3 / $2 / $1。每轮最多签一人，可 Pass 一轮。"],
            ["02", "Reveal", "揭晓真实身份与四维。STEAL / FAIR / OVERPAY —— 还有你错过的那些人。"],
            ["03", "Team Build", "剩余预算不清零：买 Rogue Buff、看阵容 Trait，决定这支队是什么类型。"],
            ["04", "Major", "瑞士轮 → 淘汰赛，逐回合直播。Firepower 决定中心值，Stability 决定波动。"],
          ].map(([n, t, d]) => (
            <div key={n} className="flex gap-4 border border-bc-line bg-bc-panel/80 p-4 backdrop-blur">
              <div className="font-display text-4xl font-black leading-none text-bc-accent/70">{n}</div>
              <div>
                <div className="font-display text-xl font-bold uppercase tracking-wider">{t}</div>
                <div className="text-sm text-bc-muted">{d}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
