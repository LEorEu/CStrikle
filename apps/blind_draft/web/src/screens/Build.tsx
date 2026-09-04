import { useMemo } from "react";
import { LowerThird } from "../components/Broadcast";
import { Button, Panel, PosTag, StatBar, GradePips } from "../components/ui";
import { BUFFS, baseTeamStats, deriveTraits, finalTeamStats, teamRating } from "../game/engine";
import type { Buff, Player } from "../game/types";
import { cn } from "../utils/cn";
import { PlayerFace } from "./Reveal";

interface Props {
  roster: Player[];
  budget: number;
  buffs: Buff[];
  onToggleBuff: (b: Buff) => void;
  onContinue: () => void;
}

const TONE = { good: "#2fe08a", bad: "#ff2d3b", neutral: "#ffb400" };

export function Build({ roster, budget, buffs, onToggleBuff, onContinue }: Props) {
  const traits = useMemo(() => deriveTraits(roster), [roster]);
  const base = useMemo(() => baseTeamStats(roster), [roster]);
  const final = useMemo(() => finalTeamStats(roster, traits, buffs), [roster, traits, buffs]);
  const spent = buffs.reduce((s, b) => s + b.cost, 0);
  const left = budget - spent;

  const rows: [string, keyof typeof base, string][] = [
    ["Firepower", "firepower", "#ff8a2a"],
    ["Tactics", "tactics", "#ffb400"],
    ["Consistency", "consistency", "#2fe08a"],
    ["Experience", "experience", "#2fa8ff"],
    ["Chemistry", "chemistry", "#d946ef"],
    ["Clutch", "clutch", "#f43f5e"],
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <LowerThird kicker="Team Build" title="Rogue Shop" sub={`剩余 $${left} · 已购 ${buffs.length} 项 · 队伍评级 ${teamRating(final).toFixed(1)}`} color="#d946ef" />
        <Button onClick={onContinue}>Lock Roster & Enter Major ▶</Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr_360px]">
        {/* Roster */}
        <Panel title="Starting Five">
          <div className="divide-y divide-bc-line">
            {roster.map((p) => (
              <div key={p.id} className="flex items-center gap-3 px-3 py-2.5">
                <PlayerFace p={p} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-display text-lg font-black leading-none">{p.nick}</span>
                    <span className="text-xs">{p.flag}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <PosTag pos={p.position} />
                    <GradePips grade={p.grade} />
                  </div>
                </div>
                <div className="text-right font-mono text-[10px] leading-tight text-bc-muted">
                  <div>
                    F<span className="text-bc-text">{p.attrs.firepower}</span> L<span className="text-bc-text">{p.attrs.leadership}</span>
                  </div>
                  <div>
                    E<span className="text-bc-text">{p.attrs.experience}</span> S<span className="text-bc-text">{p.attrs.stability}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="border-t border-bc-line bg-bc-panel2 px-3 py-2">
            <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">Free Traits</div>
            <div className="mt-2 space-y-2">
              {traits.length === 0 && <div className="text-xs text-bc-muted">这套阵容没有触发任何 Trait。</div>}
              {traits.map((t) => (
                <div key={t.id} className="flex items-start gap-2">
                  <span className="mt-1 h-2 w-2 shrink-0" style={{ background: TONE[t.tone] }} />
                  <div>
                    <div className="font-display text-sm font-bold uppercase tracking-wider" style={{ color: TONE[t.tone] }}>
                      {t.name}
                    </div>
                    <div className="text-xs text-bc-muted">{t.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Panel>

        {/* Shop */}
        <Panel title="Rogue Buffs" right={<span className="font-mono text-xs text-bc-muted">Budget ${left}</span>}>
          <div className="grid gap-2 p-3 sm:grid-cols-2">
            {BUFFS.map((b) => {
              const owned = buffs.some((x) => x.id === b.id);
              const affordable = owned || b.cost <= left;
              return (
                <button
                  key={b.id}
                  disabled={!affordable}
                  onClick={() => onToggleBuff(b)}
                  className={cn(
                    "flex items-start gap-3 border p-3 text-left transition-all",
                    owned ? "border-bc-accent bg-bc-accent/10" : "border-bc-line bg-bc-panel2 hover:border-bc-muted",
                    !affordable && "cursor-not-allowed opacity-35",
                  )}
                >
                  <div className="text-2xl">{b.icon}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <div className="truncate font-display text-base font-bold uppercase tracking-wider">{b.name}</div>
                      <div className="cut-corner shrink-0 bg-bc-accent px-2 font-display text-sm font-black text-bc-bg">${b.cost}</div>
                    </div>
                    <div className="text-xs text-bc-muted">{b.desc}</div>
                    {owned && <div className="mt-1 font-display text-[10px] font-black uppercase tracking-[0.3em] text-bc-accent">Equipped · click to refund</div>}
                  </div>
                </button>
              );
            })}
          </div>
        </Panel>

        {/* Derived */}
        <Panel title="Team Profile">
          <div className="space-y-3 p-3">
            {rows.map(([label, key, color]) => {
              const b = base[key] as number;
              const f = final[key] as number;
              const d = f - b;
              return (
                <div key={key}>
                  <div className="flex items-center justify-between font-display text-xs font-bold uppercase tracking-[0.25em] text-bc-muted">
                    <span>{label}</span>
                    <span className={cn("font-mono", d > 0.05 && "text-bc-green", d < -0.05 && "text-bc-live")}>
                      {d > 0.05 ? `+${d.toFixed(1)}` : d < -0.05 ? d.toFixed(1) : "—"}
                    </span>
                  </div>
                  <StatBar label="" value={f} color={color} compact />
                </div>
              );
            })}
            <div className="border-t border-bc-line pt-3">
              <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">Map Pool Bonus</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {Object.keys(final.mapBonus).length === 0 && <span className="text-xs text-bc-muted">无地图特化</span>}
                {Object.entries(final.mapBonus).map(([m, v]) => (
                  <span key={m} className="border border-bc-line px-2 py-0.5 font-mono text-xs">
                    {m} <span className="text-bc-green">+{v}</span>
                  </span>
                ))}
              </div>
            </div>
            <div className="border-t border-bc-line pt-3">
              <div className="font-display text-[10px] font-bold uppercase tracking-[0.35em] text-bc-muted">Projected Team Rating</div>
              <div className="font-display text-5xl font-black text-bc-accent">{teamRating(final).toFixed(1)}</div>
              <div className="text-xs text-bc-muted">Major 参赛队评级区间约 53 ~ 73。淘汰赛中 Experience 额外加权。</div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
