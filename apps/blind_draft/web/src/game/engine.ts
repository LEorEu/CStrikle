import { PLAYERS } from "../data/players";
import type {
  Buff,
  ClueType,
  DraftCard,
  Grade,
  MapResult,
  MatchDef,
  MatchOutcome,
  OpponentTeam,
  Player,
  PlayerMapStat,
  Position,
  Price,
  RoundResult,
  TeamStats,
  Trait,
  ValueTag,
} from "./types";

export const BUDGET = 15;
export const ROUNDS = 6;
export const ROSTER_SIZE = 5;
export const MAPS = ["Mirage", "Inferno", "Nuke", "Ancient", "Anubis", "Dust2", "Overpass"];

const rnd = Math.random;
export const pick = <T,>(arr: T[]): T => arr[Math.floor(rnd() * arr.length)];
export const shuffle = <T,>(arr: T[]): T[] => {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

// ---------- Market price ----------
export function rollPrice(p: Player): Price {
  let price: number = p.grade;
  const r = rnd();
  if (r < 0.2) price -= 1; // market undervalues
  else if (r > 0.93 && p.grade <= 3) price += 1; // rare overvalue (OVERPAY trap)
  if (p.position === "IGL") price = Math.min(price, 3);
  return Math.max(1, Math.min(5, price)) as Price;
}

// ---------- Clues ----------
const CLUE_TYPES: ClueType[] = ["country", "club", "age", "majors", "champs"];

export function clueText(p: Player, t: ClueType): string {
  switch (t) {
    case "country":
      return `${p.flag} ${p.country}`;
    case "club":
      return `🏷️ ${p.club}`;
    case "age":
      return `🎂 Age ${p.age}`;
    case "majors":
      return `🏟️ Major ×${p.majors}`;
    case "champs":
      return `🏆 Major Titles ×${p.champs}`;
  }
}

function clueStrength(p: Player, t: ClueType): number {
  // rough "how informative is this clue" score — dead clues score ~0
  switch (t) {
    case "champs":
      return p.champs === 0 ? 0.05 : 0.9;
    case "majors":
      return p.majors === 0 ? 0.15 : Math.min(1, 0.3 + p.majors / 15);
    case "age":
      return p.age <= 21 || p.age >= 31 ? 0.6 : 0.3;
    case "club":
      return 0.65;
    case "country":
      return 0.45;
  }
}

function assignClues(players: Player[]): ClueType[] {
  // tiny 5x5 assignment: try permutations, maximise total strength, forbid dead clues when possible
  let best: ClueType[] = [...CLUE_TYPES];
  let bestScore = -1;
  const perm = (arr: ClueType[], m: ClueType[] = []) => {
    if (arr.length === 0) {
      const score = m.reduce((s, t, i) => s + clueStrength(players[i], t) + rnd() * 0.15, 0);
      if (score > bestScore) {
        bestScore = score;
        best = [...m];
      }
      return;
    }
    for (let i = 0; i < arr.length; i++) {
      const rest = [...arr.slice(0, i), ...arr.slice(i + 1)];
      perm(rest, [...m, arr[i]]);
    }
  };
  perm(CLUE_TYPES);
  return best;
}

// ---------- Board ----------
export function generateBoards(): DraftCard[][] {
  const pool = shuffle(PLAYERS);
  const used = new Set<string>();
  const boards: DraftCard[][] = [];

  for (let r = 1; r <= ROUNDS; r++) {
    const bySlot: (Player | null)[] = [null, null, null, null, null];
    // roll prices for remaining pool, fill each price slot
    const candidates = shuffle(pool.filter((p) => !used.has(p.id)));
    const priced = candidates.map((p) => ({ p, price: rollPrice(p) }));
    for (let price = 5; price >= 1; price--) {
      const found = priced.find((x) => x.price === price && !used.has(x.p.id));
      if (found) {
        bySlot[5 - price] = found.p;
        used.add(found.p.id);
      } else {
        // fallback: take closest grade
        const fb = candidates.find((p) => !used.has(p.id) && Math.abs(p.grade - price) <= 1);
        if (fb) {
          bySlot[5 - price] = fb;
          used.add(fb.id);
        }
      }
    }
    const players = bySlot.filter(Boolean) as Player[];
    const clues = assignClues(players);
    boards.push(
      players.map((p, i) => ({
        id: `${r}-${p.id}`,
        player: p,
        price: (5 - i) as Price,
        clueType: clues[i],
        clueText: clueText(p, clues[i]),
        round: r,
      })),
    );
  }
  return boards;
}

// ---------- Valuation ----------
export function fairPrice(value: number): Price {
  if (value < 50) return 1;
  if (value < 59) return 2;
  if (value < 71) return 3;
  if (value < 81) return 4;
  return 5;
}
export function valueTag(p: Player, price: Price): ValueTag {
  const diff = fairPrice(p.value) - price;
  if (diff >= 1) return "STEAL";
  if (diff <= -1) return "OVERPAY";
  return "FAIR";
}
export function valueDelta(p: Player, price: Price): number {
  return fairPrice(p.value) - price;
}

export function canAfford(price: number, budget: number, signed: number): boolean {
  const remainingAfter = ROSTER_SIZE - signed - 1;
  return budget - price >= remainingAfter;
}

// ---------- Team derived stats ----------
export function baseTeamStats(roster: Player[]): TeamStats {
  const n = Math.max(1, roster.length);
  const avg = (f: (p: Player) => number) => roster.reduce((s, p) => s + f(p), 0) / n;
  const igl = roster.filter((p) => p.position === "IGL");
  const leadMax = Math.max(0, ...roster.map((p) => p.attrs.leadership));
  const tactics = leadMax * 0.7 + avg((p) => p.attrs.experience) * 0.3 - (igl.length === 0 ? 10 : 0);
  return {
    firepower: avg((p) => p.attrs.firepower),
    tactics,
    consistency: avg((p) => p.attrs.stability),
    experience: avg((p) => p.attrs.experience),
    chemistry: 50,
    clutch: avg((p) => p.attrs.firepower * 0.5 + p.attrs.stability * 0.5),
    mapBonus: {},
  };
}

export function deriveTraits(roster: Player[]): Trait[] {
  const traits: Trait[] = [];
  const countOf = (f: (p: Player) => string) => {
    const m: Record<string, number> = {};
    roster.forEach((p) => (m[f(p)] = (m[f(p)] ?? 0) + 1));
    return m;
  };
  const byCountry = countOf((p) => p.country);
  const byClub = countOf((p) => p.club);
  const igls = roster.filter((p) => p.position === "IGL").length;
  const awps = roster.filter((p) => p.position === "AWPER").length;
  const avgAge = roster.reduce((s, p) => s + p.age, 0) / roster.length;
  const avgMajors = roster.reduce((s, p) => s + p.majors, 0) / roster.length;
  const champs = roster.reduce((s, p) => s + p.champs, 0);

  for (const [c, n] of Object.entries(byCountry)) {
    if (n >= 3)
      traits.push({
        id: `nat-${c}`,
        name: `${c} Core`,
        desc: `${n} 名 ${c} 选手 · 沟通无障碍`,
        tone: "good",
        apply: (t) => ({ ...t, chemistry: t.chemistry + 12, consistency: t.consistency + 3 }),
      });
  }
  for (const [c, n] of Object.entries(byClub)) {
    if (n >= 2)
      traits.push({
        id: `club-${c}`,
        name: `Ex-${c} Duo`,
        desc: `${n} 名前 ${c} 队友 · 默契体系`,
        tone: "good",
        apply: (t) => ({ ...t, chemistry: t.chemistry + 6, tactics: t.tactics + 3 }),
      });
  }
  if (igls === 0)
    traits.push({
      id: "no-igl",
      name: "Headless",
      desc: "没有指挥 · 战术组织严重受损",
      tone: "bad",
      apply: (t) => ({ ...t, tactics: t.tactics - 12, consistency: t.consistency - 6 }),
    });
  if (igls >= 2)
    traits.push({
      id: "two-igl",
      name: "Too Many Cooks",
      desc: "双指挥 · 火力被稀释",
      tone: "bad",
      apply: (t) => ({ ...t, firepower: t.firepower - 4, chemistry: t.chemistry - 6 }),
    });
  if (awps === 0)
    traits.push({
      id: "no-awp",
      name: "Rifle Only",
      desc: "无狙击手 · 对狙对局吃亏",
      tone: "bad",
      apply: (t) => ({ ...t, firepower: t.firepower - 3, clutch: t.clutch - 3 }),
    });
  if (awps >= 2)
    traits.push({
      id: "double-awp",
      name: "Double AWP",
      desc: "双狙 · 上限拉高但更不稳定",
      tone: "neutral",
      apply: (t) => ({ ...t, firepower: t.firepower + 4, consistency: t.consistency - 7 }),
    });
  if (avgAge <= 23)
    traits.push({
      id: "young-guns",
      name: "Young Guns",
      desc: `平均年龄 ${avgAge.toFixed(1)} · 爆种上限`,
      tone: "neutral",
      apply: (t) => ({ ...t, firepower: t.firepower + 3, consistency: t.consistency - 5, clutch: t.clutch + 4 }),
    });
  if (avgMajors >= 10)
    traits.push({
      id: "veterans",
      name: "Battle-Hardened",
      desc: `场均 ${avgMajors.toFixed(1)} 次 Major · 大场面不慌`,
      tone: "good",
      apply: (t) => ({ ...t, experience: t.experience + 6, consistency: t.consistency + 4 }),
    });
  if (champs >= 6)
    traits.push({
      id: "dynasty",
      name: "Dynasty DNA",
      desc: `合计 ${champs} 座 Major 冠军 · 冠军基因`,
      tone: "good",
      apply: (t) => ({ ...t, clutch: t.clutch + 8, tactics: t.tactics + 3 }),
    });
  const g1 = roster.filter((p) => p.grade === 1).length;
  if (g1 >= 3)
    traits.push({
      id: "underdogs",
      name: "Cinderella Story",
      desc: `${g1} 名无名之辈 · 没人研究过你们`,
      tone: "neutral",
      apply: (t) => ({ ...t, clutch: t.clutch + 6, tactics: t.tactics + 2 }),
    });
  return traits;
}

export const BUFFS: Buff[] = [
  {
    id: "bootcamp",
    name: "Two-Week Bootcamp",
    cost: 2,
    icon: "🏕️",
    desc: "全队 Consistency +8，Chemistry +10",
    apply: (t) => ({ ...t, consistency: t.consistency + 8, chemistry: t.chemistry + 10 }),
  },
  {
    id: "coach",
    name: "Veteran Coach",
    cost: 3,
    icon: "📋",
    desc: "Tactics +10，Experience +8。淘汰赛中额外生效",
    apply: (t) => ({ ...t, tactics: t.tactics + 10, experience: t.experience + 8 }),
  },
  {
    id: "awp-setup",
    name: "Star AWP Setup",
    cost: 3,
    icon: "🎯",
    desc: "若阵容有 AWPER：Firepower +5，Clutch +4",
    apply: (t, r) => (r.some((p) => p.position === "AWPER") ? { ...t, firepower: t.firepower + 5, clutch: t.clutch + 4 } : t),
  },
  {
    id: "analyst",
    name: "Analyst Desk",
    cost: 2,
    icon: "🧠",
    desc: "解锁 Anti-Strat：Tactics +5，对手 Consistency 视为 -4",
    apply: (t) => ({ ...t, tactics: t.tactics + 5 }),
  },
  {
    id: "mirage",
    name: "Map Specialist: Mirage",
    cost: 1,
    icon: "🗺️",
    desc: "Mirage 上 Firepower +7",
    apply: (t) => ({ ...t, mapBonus: { ...t.mapBonus, Mirage: 7 } }),
  },
  {
    id: "nuke",
    name: "Map Specialist: Nuke",
    cost: 1,
    icon: "☢️",
    desc: "Nuke 上 Firepower +7",
    apply: (t) => ({ ...t, mapBonus: { ...t.mapBonus, Nuke: 7 } }),
  },
  {
    id: "inferno",
    name: "Map Specialist: Inferno",
    cost: 1,
    icon: "🔥",
    desc: "Inferno 上 Firepower +7",
    apply: (t) => ({ ...t, mapBonus: { ...t.mapBonus, Inferno: 7 } }),
  },
  {
    id: "clutch",
    name: "Clutch Gene",
    cost: 2,
    icon: "💎",
    desc: "Clutch +10：落后时的翻盘概率提升",
    apply: (t) => ({ ...t, clutch: t.clutch + 10 }),
  },
  {
    id: "loud-igl",
    name: "Mic Discipline",
    cost: 2,
    icon: "🎙️",
    desc: "若阵容有 IGL：Tactics +7，Consistency +3",
    apply: (t, r) => (r.some((p) => p.position === "IGL") ? { ...t, tactics: t.tactics + 7, consistency: t.consistency + 3 } : t),
  },
  {
    id: "sponsor",
    name: "Energy Drink Sponsor",
    cost: 1,
    icon: "⚡",
    desc: "Firepower +3。就这么多。",
    apply: (t) => ({ ...t, firepower: t.firepower + 3 }),
  },
  {
    id: "psych",
    name: "Sports Psychologist",
    cost: 4,
    icon: "🧘",
    desc: "Consistency +12，Clutch +8，Chemistry +8",
    apply: (t) => ({ ...t, consistency: t.consistency + 12, clutch: t.clutch + 8, chemistry: t.chemistry + 8 }),
  },
  {
    id: "superstar",
    name: "Star Treatment",
    cost: 3,
    icon: "⭐",
    desc: "围绕头牌建队：Firepower +3，Clutch +6",
    apply: (t) => ({ ...t, firepower: t.firepower + 3, clutch: t.clutch + 6 }),
  },
];

export function finalTeamStats(roster: Player[], traits: Trait[], buffs: Buff[]): TeamStats {
  let t = baseTeamStats(roster);
  traits.forEach((tr) => (t = tr.apply(t)));
  buffs.forEach((b) => (t = b.apply(t, roster)));
  return t;
}

export function teamRating(t: TeamStats): number {
  return t.firepower * 0.5 + t.tactics * 0.22 + t.consistency * 0.13 + t.chemistry * 0.08 + t.experience * 0.07;
}

// ---------- Opponents ----------
const OPP_NAMES: [string, string, string, string][] = [
  ["Nordlys Esports", "NLS", "EU", "#e11d48"],
  ["Vortex Gaming", "VTX", "CIS", "#eab308"],
  ["Meridian", "MRD", "CIS", "#3b82f6"],
  ["Ember Squad", "EMB", "EU", "#f97316"],
  ["Legion Nine", "LGN", "EU", "#a855f7"],
  ["Sertão Clan", "SRT", "SA", "#22c55e"],
  ["Silesia Eagles", "SLE", "EU", "#ef4444"],
  ["Redline", "RDL", "EU", "#dc2626"],
  ["Ghostline", "GHL", "EU", "#94a3b8"],
  ["Astra Nova", "AST", "EU", "#06b6d4"],
  ["Liberty Esports", "LBT", "NA", "#1d4ed8"],
  ["Steppe Wolves", "STP", "ASIA", "#84cc16"],
  ["Southern Cross", "SCX", "OCE", "#14b8a6"],
  ["Ironclad", "IRC", "EU", "#78716c"],
  ["Monarch", "MON", "NA", "#d946ef"],
];

export function generateOpponents(exclude: Set<string> = new Set()): OpponentTeam[] {
  const ratings = shuffle([73, 71, 69, 68, 67, 66, 65, 64, 63, 62, 61, 60, 58, 56, 53]);
  return OPP_NAMES.map(([name, tag, region, color], i) => ({
    id: tag,
    name,
    tag,
    region,
    color,
    rating: ratings[i] + (rnd() * 4 - 2),
    consistency: 55 + rnd() * 30,
    players: shuffle(PLAYERS.filter((p) => !exclude.has(p.id) && p.club.toLowerCase().startsWith(name.split(" ")[0].toLowerCase().slice(0, 4))))
      .slice(0, 5)
      .map((p) => p.nick),
  })).map((o) => {
    while (o.players.length < 5) o.players.push(pick(["fr0st", "zeta", "kwon", "riX", "duke", "ghost", "vamp", "oak", "lux", "byte"]) + (o.players.length + 1));
    return o;
  });
}

// ---------- Match simulation ----------
const EVENTS_WIN = [
  "{p} 首杀打开局面，{t} 顺势拿下",
  "{p} 残局 1v2 完成 Clutch！",
  "{t} 默认站位后爆弹，{p} 三杀收尾",
  "{p} 狙击线上双杀，{t} 干净利落",
  "回防及时，{p} 拆弹成功",
  "{t} 经济压制，{p} 手枪也能拿人头",
  "{p} 闪光配合完美，{t} 拿下回合",
  "{p} 补枪稳健，{t} 收下这一回合",
  "{t} 快攻 B 区，{p} 收获 ACE 级表现",
  "{p} 关键 Lurk 得手，{t} 拿到回合",
];

function eventText(p: string, team: string) {
  return pick(EVENTS_WIN).replace("{p}", p).replace("{t}", team);
}

function gauss() {
  let u = 0,
    v = 0;
  while (u === 0) u = rnd();
  while (v === 0) v = rnd();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export function simulateMap(
  map: string,
  home: { roster: Player[]; stats: TeamStats; name: string; buffs: Buff[] },
  away: OpponentTeam,
  playoff: boolean,
): MapResult {
  const rounds: RoundResult[] = [];
  let hs = 0,
    as = 0;
  let target = 13;
  const homeStats: PlayerMapStat[] = home.roster.map((p) => ({ id: p.id, nick: p.nick, kills: 0, deaths: 0 }));
  const awayStats: PlayerMapStat[] = away.players.map((n, i) => ({ id: `${away.id}-${i}`, nick: n, kills: 0, deaths: 0 }));
  const hasAnalyst = home.buffs.some((b) => b.id === "analyst");

  const homeBase =
    teamRating(home.stats) + (home.stats.mapBonus[map] ?? 0) * 0.5 + (playoff ? (home.stats.experience - 50) * 0.08 : 0);
  const awayBase = away.rating;
  const homeNoise = (100 - home.stats.consistency) / 100 * 9;
  const awayNoise = (100 - (away.consistency - (hasAnalyst ? 4 : 0))) / 100 * 9;

  let n = 0;
  while (hs < target && as < target) {
    n++;
    // clutch factor when behind
    const deficit = as - hs;
    const clutch = deficit >= 3 ? (home.stats.clutch - 60) * 0.15 : 0;
    // loss bonus momentum
    const lastThree = rounds.slice(-3);
    const homeLossStreak = lastThree.length === 3 && lastThree.every((r) => r.winner === "away");
    const awayLossStreak = lastThree.length === 3 && lastThree.every((r) => r.winner === "home");
    const h = homeBase + clutch + gauss() * homeNoise + (homeLossStreak ? 1.5 : 0);
    const a = awayBase + gauss() * awayNoise + (awayLossStreak ? 1.5 : 0);
    const pHome = 1 / (1 + Math.exp(-(h - a) / 12));
    const winner: "home" | "away" = rnd() < pHome ? "home" : "away";
    if (winner === "home") hs++;
    else as++;

    // distribute frags
    const winKills = 3 + Math.floor(rnd() * 3); // 3-5
    const loseKills = Math.floor(rnd() * 4); // 0-3
    const wStats = winner === "home" ? homeStats : awayStats;
    const lStats = winner === "home" ? awayStats : homeStats;
    const wRoster = winner === "home" ? home.roster : null;
    const weightFor = (i: number) => (wRoster ? wRoster[i].attrs.firepower : 60 + (i === 0 ? 15 : 0));
    const distribute = (stats: PlayerMapStat[], kills: number, weights: number[]) => {
      const total = weights.reduce((x, y) => x + y, 0);
      for (let k = 0; k < kills; k++) {
        let r = rnd() * total;
        for (let i = 0; i < stats.length; i++) {
          r -= weights[i];
          if (r <= 0) {
            stats[i].kills++;
            break;
          }
        }
      }
    };
    distribute(wStats, winKills, wStats.map((_, i) => weightFor(i)));
    distribute(lStats, loseKills, lStats.map((_, i) => (winner === "away" ? home.roster[i].attrs.firepower : 60 + (i === 0 ? 15 : 0))));
    // deaths: losers lose ~ winKills players, winners lose loseKills
    const shuffledL = shuffle(lStats.map((_, i) => i)).slice(0, Math.min(5, winKills));
    shuffledL.forEach((i) => lStats[i].deaths++);
    const shuffledW = shuffle(wStats.map((_, i) => i)).slice(0, Math.min(5, loseKills));
    shuffledW.forEach((i) => wStats[i].deaths++);

    const star = winner === "home" ? pick(wStats.slice().sort((x, y) => y.kills - x.kills).slice(0, 3)).nick : pick(awayStats).nick;
    rounds.push({
      n,
      winner,
      homeScore: hs,
      awayScore: as,
      event: eventText(star, winner === "home" ? home.name : away.tag),
    });
    if (hs === target - 1 && as === target - 1) target += 3; // overtime
    if (n > 60) break;
  }
  return { map, homeScore: hs, awayScore: as, winner: hs > as ? "home" : "away", rounds, homeStats, awayStats };
}

export function pickMaps(bo: number, team: TeamStats): string[] {
  // Team bans weak maps, prefers bonus maps
  const preferred = MAPS.filter((m) => (team.mapBonus[m] ?? 0) > 0);
  const others = shuffle(MAPS.filter((m) => !preferred.includes(m)));
  const order = [...shuffle(preferred), ...others];
  if (bo === 1) return [rnd() < 0.5 && preferred.length ? preferred[0] : others[0]];
  return order.slice(0, bo);
}

export function simulateMatch(
  def: MatchDef,
  home: { roster: Player[]; stats: TeamStats; name: string; buffs: Buff[] },
): MatchOutcome {
  const maps = pickMaps(def.bo, home.stats);
  const need = Math.ceil(def.bo / 2);
  const results: MapResult[] = [];
  let hm = 0,
    am = 0;
  const playoff = def.stage === "Playoffs";
  for (const m of maps) {
    if (hm === need || am === need) break;
    const r = simulateMap(m, home, def.opponent, playoff);
    results.push(r);
    if (r.winner === "home") hm++;
    else am++;
  }
  return { def, maps: results, homeMaps: hm, awayMaps: am, won: hm > am };
}

// ---------- Swiss helpers ----------
export function gradeLabel(g: Grade) {
  return `G${g}`;
}
export const POS_COLOR: Record<Position, string> = {
  IGL: "#ffb400",
  AWPER: "#2fa8ff",
  RIFLER: "#2fe08a",
};
