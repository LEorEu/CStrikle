import { LowerThird } from "../components/Broadcast";
import { Button, Panel, PosTag, PriceBadge, ValueTagBadge } from "../components/ui";
import { fairPrice, valueTag } from "../game/engine";
import type { Buff, SignedCard } from "../game/types";
import { PlayerFace } from "./Reveal";
import type { TournamentResult } from "./Tournament";
import { cn } from "../utils/cn";

interface Props {
  result: TournamentResult;
  signed: SignedCard[];
  buffs: Buff[];
  teamName: string;
  onRestart: () => void;
}

export function Final({ result, signed, buffs, teamName, onRestart }: Props) {
  const champion = result.placementRank === 1;
  const totalMaps = result.history.reduce((s, h) => s + h.maps.length, 0);
  const mapsWon = result.history.reduce((s, h) => s + h.homeMaps, 0);
  // MVP: most kills across all maps
  const kills: Record<string, number> = {};
  const deaths: Record<string, number> = {};
  result.history.forEach((h) =>
    h.maps.forEach((m) =>
      m.homeStats.forEach((s) => {
        kills[s.nick] = (kills[s.nick] ?? 0) + s.kills;
        deaths[s.nick] = (deaths[s.nick] ?? 0) + s.deaths;
      }),
    ),
  );
  const mvp = Object.entries(kills).sort((a, b) => b[1] - a[1])[0];
  const spent = signed.reduce((s, c) => s + c.price, 0);
  const buffSpent = buffs.reduce((s, b) => s + b.cost, 0);

  return (
    <div className="space-y-5">
      <div className={cn("relative overflow-hidden border p-8", champion ? "border-bc-accent bg-[radial-gradient(ellipse_at_top,rgba(255,180,0,0.25),transparent_60%)]" : "border-bc-line bg-bc-panel")}>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <LowerThird kicker="Post-Match Show" title={result.placement} sub={`${teamName} · Swiss ${result.swissRecord} · 地图 ${mapsWon}/${totalMaps}`} color={champion ? "#ffb400" : "#ff2d3b"} />
            {champion && <div className="mt-4 font-display text-7xl font-black uppercase tracking-tight text-bc-accent animate-pop">🏆 Major Champions</div>}
          </div>
          <Button onClick={onRestart}>Run It Back ▶</Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Panel title="Draft Recap">
          <div className="divide-y divide-bc-line">
            {signed.map((c) => {
              const tag = valueTag(c.player, c.price);
              const k = kills[c.player.nick] ?? 0;
              const d = deaths[c.player.nick] ?? 0;
              return (
                <div key={c.id} className="flex items-center gap-4 px-4 py-3">
                  <PriceBadge price={c.price} size="sm" />
                  <PlayerFace p={c.player} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-display text-xl font-black">{c.player.nick}</span>
                      <span>{c.player.flag}</span>
                      <PosTag pos={c.player.position} />
                      {mvp && mvp[0] === c.player.nick && <span className="skew-tag bg-bc-accent px-2 font-display text-[10px] font-black text-bc-bg">MVP</span>}
                    </div>
                    <div className="font-mono text-[11px] text-bc-muted">
                      R{c.pickedRound} · 线索「{c.clueText}」 · fair ${fairPrice(c.player.value)} · VAL {c.player.value}
                    </div>
                  </div>
                  <div className="text-right font-mono text-sm">
                    <div>
                      {k} / {d}
                    </div>
                    <div className={cn("text-xs", k - d >= 0 ? "text-bc-green" : "text-bc-live")}>{k - d >= 0 ? `+${k - d}` : k - d}</div>
                  </div>
                  <ValueTagBadge tag={tag} />
                </div>
              );
            })}
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="Economy">
            <div className="space-y-2 p-4 font-mono text-sm">
              <Row k="Players" v={`$${spent}`} />
              <Row k="Rogue Buffs" v={`$${buffSpent}`} />
              <Row k="Unspent" v={`$${15 - spent - buffSpent}`} />
              <div className="border-t border-bc-line pt-2">
                {buffs.length === 0 && <div className="text-xs text-bc-muted">未购买任何 Buff</div>}
                {buffs.map((b) => (
                  <div key={b.id} className="text-xs text-bc-muted">
                    {b.icon} {b.name}
                  </div>
                ))}
              </div>
            </div>
          </Panel>
          <Panel title="Results">
            <div className="divide-y divide-bc-line">
              {result.history.map((h, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-2 text-sm">
                  <span className={cn("w-10 font-display font-black", h.won ? "text-bc-green" : "text-bc-live")}>{h.won ? "W" : "L"}</span>
                  <span className="flex-1 truncate text-bc-muted">{h.def.label}</span>
                  <span className="font-mono">
                    {h.homeMaps}-{h.awayMaps}
                  </span>
                  <span className="w-12 text-right font-display font-bold" style={{ color: h.def.opponent.color }}>
                    {h.def.opponent.tag}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-bc-muted">{k}</span>
      <span>{v}</span>
    </div>
  );
}
