import type { Attributes, Grade, Player, Position } from "../game/types";

// ---- deterministic RNG (card generation RNG: runs once, results are fixed) ----
function hash(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
function seeded(seed: number) {
  let s = seed || 1;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 10000) / 10000;
  };
}

const TEMPLATE: Record<Position, Record<Grade, Attributes>> = {
  RIFLER: {
    1: { firepower: 52, leadership: 20, experience: 20, stability: 48 },
    2: { firepower: 60, leadership: 22, experience: 34, stability: 56 },
    3: { firepower: 70, leadership: 24, experience: 48, stability: 65 },
    4: { firepower: 80, leadership: 27, experience: 62, stability: 75 },
    5: { firepower: 89, leadership: 30, experience: 75, stability: 84 },
  },
  AWPER: {
    1: { firepower: 52, leadership: 18, experience: 20, stability: 51 },
    2: { firepower: 60, leadership: 20, experience: 34, stability: 60 },
    3: { firepower: 70, leadership: 22, experience: 48, stability: 70 },
    4: { firepower: 80, leadership: 24, experience: 62, stability: 80 },
    5: { firepower: 89, leadership: 26, experience: 75, stability: 88 },
  },
  IGL: {
    1: { firepower: 45, leadership: 56, experience: 25, stability: 50 },
    2: { firepower: 49, leadership: 65, experience: 38, stability: 57 },
    3: { firepower: 54, leadership: 75, experience: 52, stability: 64 },
    4: { firepower: 60, leadership: 84, experience: 65, stability: 71 },
    5: { firepower: 66, leadership: 90, experience: 76, stability: 77 },
  },
};

export const WEIGHTS: Record<Position, Attributes> = {
  RIFLER: { firepower: 0.55, experience: 0.2, stability: 0.2, leadership: 0.05 },
  AWPER: { firepower: 0.45, stability: 0.3, experience: 0.2, leadership: 0.05 },
  IGL: { leadership: 0.35, experience: 0.35, firepower: 0.25, stability: 0.05 },
};

const FLAGS: Record<string, string> = {
  Denmark: "🇩🇰", Sweden: "🇸🇪", France: "🇫🇷", Brazil: "🇧🇷", Ukraine: "🇺🇦", Russia: "🇷🇺",
  Poland: "🇵🇱", USA: "🇺🇸", Canada: "🇨🇦", Finland: "🇫🇮", Bosnia: "🇧🇦", Kazakhstan: "🇰🇿",
  Israel: "🇮🇱", Germany: "🇩🇪", Spain: "🇪🇸", Slovakia: "🇸🇰", Mongolia: "🇲🇳", Australia: "🇦🇺",
  Latvia: "🇱🇻", Lithuania: "🇱🇹", Estonia: "🇪🇪", Turkey: "🇹🇷", Serbia: "🇷🇸", Argentina: "🇦🇷",
  China: "🇨🇳", Netherlands: "🇳🇱", Belgium: "🇧🇪", Norway: "🇳🇴", UK: "🇬🇧", Portugal: "🇵🇹",
  Romania: "🇷🇴", Hungary: "🇭🇺", Czechia: "🇨🇿", Bulgaria: "🇧🇬", Slovenia: "🇸🇮",
};

type Def = [nick: string, country: string, club: string, age: number, majors: number, champs: number, top20: number[], pos: Position];

// Fictional player pool. Grade is derived from evidence (top20 / majors / champs) per design doc.
const DEFS: Def[] = [
  // ---- G5 candidates (Top5 finishes) ----
  ["kaiZer", "Denmark", "Nordlys", 27, 14, 4, [1, 2, 4, 8], "RIFLER"],
  ["Zephyr", "Ukraine", "Vortex", 28, 12, 1, [1, 1, 3], "RIFLER"],
  ["dropz", "Russia", "Meridian", 24, 6, 2, [2, 5, 9], "AWPER"],
  ["NoVa", "France", "Ember", 30, 16, 2, [2, 6, 11, 14], "AWPER"],
  ["Rook", "Sweden", "Legion", 31, 18, 3, [4, 7, 12], "RIFLER"],
  ["Halcyon", "Slovakia", "Vortex", 25, 8, 1, [3, 5, 10], "RIFLER"],
  ["hexa", "Bosnia", "Redline", 29, 13, 0, [5, 8, 15], "RIFLER"],
  ["Sable", "Kazakhstan", "Meridian", 26, 7, 1, [4, 9], "RIFLER"],
  ["frostbyte", "Denmark", "Nordlys", 28, 15, 4, [2, 3, 6, 10], "AWPER"],
  ["Kolt", "Israel", "Legion", 26, 9, 0, [1, 4, 6], "RIFLER"],
  // ---- G4 (2+ top20, never top5) ----
  ["Marlow", "Brazil", "Sertão", 29, 15, 2, [7, 11, 16], "RIFLER"],
  ["Wren", "Denmark", "Nordlys", 27, 14, 4, [9, 13, 18], "RIFLER"],
  ["pixL", "Finland", "Ghostline", 24, 6, 0, [6, 12], "RIFLER"],
  ["Sokol", "Russia", "Meridian", 23, 5, 1, [8, 14], "RIFLER"],
  ["Tarn", "Latvia", "Redline", 27, 10, 0, [10, 17], "AWPER"],
  ["Gale", "Sweden", "Legion", 33, 19, 3, [6, 9, 19], "RIFLER"],
  ["Orbit", "Poland", "Silesia", 34, 20, 4, [11, 15], "RIFLER"],
  ["Cinder", "France", "Ember", 25, 7, 1, [7, 13], "RIFLER"],
  ["Mako", "Brazil", "Sertão", 26, 9, 2, [10, 16], "AWPER"],
  ["Vesper", "Ukraine", "Vortex", 29, 11, 1, [12, 18, 20], "RIFLER"],
  ["Rho", "Mongolia", "Steppe", 24, 5, 0, [9, 15], "RIFLER"],
  ["Nyx", "Turkey", "Ghostline", 27, 8, 0, [13, 17], "AWPER"],
  // ---- G3-A (1 top20) ----
  ["Basalt", "Serbia", "Redline", 26, 6, 0, [14], "RIFLER"],
  ["Tempo", "USA", "Liberty", 25, 7, 0, [16], "RIFLER"],
  ["Lumen", "Germany", "Astra", 28, 9, 0, [19], "AWPER"],
  ["Quill", "Australia", "Southern Cross", 27, 6, 0, [18], "RIFLER"],
  ["Fjord", "Norway", "Astra", 24, 4, 0, [20], "RIFLER"],
  ["Ashen", "Spain", "Ember", 22, 3, 0, [17], "RIFLER"],
  // ---- G3-B (Major finalists / champions w/o top20) ----
  ["Bastion", "Denmark", "Nordlys", 30, 13, 3, [], "IGL"],
  ["Cipher", "Ukraine", "Vortex", 31, 14, 1, [], "IGL"],
  ["Warden", "Sweden", "Legion", 32, 17, 3, [], "IGL"],
  ["Anvil", "Poland", "Silesia", 33, 18, 4, [], "IGL"],
  ["Sentry", "Brazil", "Sertão", 31, 14, 2, [], "IGL"],
  ["Ledger", "France", "Ember", 29, 12, 2, [], "IGL"],
  ["Mortar", "Russia", "Meridian", 28, 7, 2, [], "RIFLER"],
  ["Cobalt", "Denmark", "Nordlys", 26, 8, 2, [], "RIFLER"],
  ["Glint", "Kazakhstan", "Meridian", 24, 6, 1, [], "RIFLER"],
  // ---- G3-C (young w/ Major top8) ----
  ["kidd0", "Sweden", "Nordlys", 19, 2, 0, [], "RIFLER"],
  ["yuna", "China", "Steppe", 20, 2, 0, [], "AWPER"],
  ["Pulse", "Ukraine", "Vortex", 19, 1, 0, [], "RIFLER"],
  ["Nimbus", "Denmark", "Astra", 21, 3, 0, [], "RIFLER"],
  ["Rift", "Russia", "Redline", 20, 2, 0, [], "AWPER"],
  // ---- G2 (Major veterans) ----
  ["Ferrum", "Poland", "Silesia", 32, 11, 0, [], "RIFLER"],
  ["Slate", "USA", "Liberty", 30, 9, 0, [], "IGL"],
  ["Oxide", "Canada", "Liberty", 29, 8, 0, [], "AWPER"],
  ["Tundra", "Finland", "Ghostline", 31, 10, 0, [], "IGL"],
  ["Ivory", "UK", "Astra", 30, 7, 0, [], "RIFLER"],
  ["Cairn", "Estonia", "Ghostline", 28, 6, 0, [], "RIFLER"],
  ["Drift", "Australia", "Southern Cross", 29, 7, 0, [], "IGL"],
  ["Pyre", "Turkey", "Redline", 27, 5, 0, [], "RIFLER"],
  ["Static", "Germany", "Astra", 31, 9, 0, [], "RIFLER"],
  ["Ember", "Brazil", "Sertão", 30, 8, 0, [], "RIFLER"],
  ["Halo", "Argentina", "Sertão", 28, 6, 0, [], "AWPER"],
  ["Mesa", "Spain", "Ember", 29, 6, 0, [], "IGL"],
  ["Lark", "Belgium", "Vortex", 27, 5, 0, [], "RIFLER"],
  ["Onyx", "Lithuania", "Ghostline", 30, 7, 0, [], "AWPER"],
  // ---- G1 ----
  ["Fable", "Netherlands", "Astra", 23, 1, 0, [], "RIFLER"],
  ["Rune", "Sweden", "Legion", 22, 0, 0, [], "RIFLER"],
  ["Sprocket", "USA", "Liberty", 24, 2, 0, [], "IGL"],
  ["Comet", "Portugal", "Ember", 21, 0, 0, [], "AWPER"],
  ["Jinx", "Romania", "Silesia", 25, 1, 0, [], "RIFLER"],
  ["Volt", "Hungary", "Silesia", 23, 1, 0, [], "RIFLER"],
  ["Moss", "Czechia", "Astra", 26, 2, 0, [], "RIFLER"],
  ["Grail", "Bulgaria", "Redline", 24, 0, 0, [], "IGL"],
  ["Skye", "Slovenia", "Legion", 20, 0, 0, [], "RIFLER"],
  ["Tally", "Canada", "Liberty", 22, 1, 0, [], "RIFLER"],
  ["Ozone", "Mongolia", "Steppe", 21, 1, 0, [], "AWPER"],
  ["Dune", "Kazakhstan", "Steppe", 27, 3, 0, [], "RIFLER"],
  ["Keel", "Norway", "Ghostline", 25, 2, 0, [], "IGL"],
  ["Wisp", "Denmark", "Nordlys", 18, 0, 0, [], "RIFLER"],
  ["Pike", "UK", "Liberty", 26, 2, 0, [], "AWPER"],
  ["Hollow", "Serbia", "Redline", 24, 1, 0, [], "RIFLER"],
  ["Brine", "Finland", "Southern Cross", 23, 0, 0, [], "RIFLER"],
  ["Cove", "Australia", "Southern Cross", 22, 1, 0, [], "IGL"],
  ["Nova", "China", "Steppe", 19, 0, 0, [], "RIFLER"],
  ["Trace", "Latvia", "Ghostline", 27, 3, 0, [], "RIFLER"],
  ["Quartz", "Argentina", "Sertão", 25, 2, 0, [], "RIFLER"],
  ["Shard", "Israel", "Legion", 21, 0, 0, [], "AWPER"],
];

function deriveGrade(d: Def): Grade {
  const [, , , age, majors, champs, top20, pos] = d;
  if (top20.some((p) => p <= 5)) return 5;
  if (top20.length >= 2) return 4;
  if (top20.length === 1) return 3;
  if (champs >= 1) return 3; // reached Major final
  if (age <= 21 && majors >= 1 && pos !== "IGL") return 3; // young w/ Major top-8 evidence
  if (majors >= 5) return 2;
  return 1;
}

function clamp(v: number, lo = 1, hi = 99) {
  return Math.max(lo, Math.min(hi, Math.round(v)));
}

function buildPlayer(d: Def): Player {
  const [nick, country, club, age, majors, champs, top20, position] = d;
  const grade = deriveGrade(d);
  const rng = seeded(hash(nick));
  const base = TEMPLATE[position][grade];
  const jitter = (range: number) => (rng() * 2 - 1) * range;

  // Top20 -> firepower fine tune inside grade (IGL only inherits half)
  const top20Score = top20.reduce((acc, p) => acc + Math.max(0, 21 - p) / 20, 0);
  let fpMod = Math.min(7, top20Score * 2.2);
  if (position === "IGL") fpMod *= 0.5;

  // Majors -> experience (log curve)
  const expMod = Math.log2(1 + majors) * 4.2 - 6;
  // Champs -> experience + IGL leadership
  const champMod = Math.min(6, champs * 2);
  const leadMod = position === "IGL" ? Math.min(6, champs * 1.5 + Math.log2(1 + majors)) : 0;

  // Youth -> +firepower ceiling, -stability
  const young = age <= 21;
  const youthFp = young ? rng() * 8 : 0;
  const youthStab = young ? -(6 + rng() * 6) : 0;

  // Grade-dependent variance: G3 is the high-variance tier; G1/G2 hide occasional gems
  // (evidence is thin, not the player). G4/G5 are well-documented -> tighter.
  const variance: Record<Grade, number> = { 1: 5, 2: 6, 3: 8, 4: 4, 5: 3 };
  const gemRoll = rng();
  const gem = grade === 1 && gemRoll < 0.25 ? 12 + rng() * 8 : grade === 2 && gemRoll < 0.2 ? 8 + rng() * 6 : 0;
  const bust = grade === 3 && gemRoll > 0.82 ? -(5 + rng() * 5) : grade === 4 && gemRoll > 0.88 ? -5 : 0;

  const attrs: Attributes = {
    firepower: clamp(base.firepower + fpMod + youthFp + gem + bust + jitter(variance[grade])),
    leadership: clamp(base.leadership + leadMod + jitter(3)),
    experience: clamp(base.experience + expMod + champMod + jitter(3)),
    stability: clamp(base.stability + youthStab + (gem ? 4 : 0) + jitter(variance[grade] + 2)),
  };

  const w = WEIGHTS[position];
  const value = clamp(
    attrs.firepower * w.firepower +
      attrs.leadership * w.leadership +
      attrs.experience * w.experience +
      attrs.stability * w.stability,
  );

  return {
    id: nick.toLowerCase(),
    nick,
    country,
    flag: FLAGS[country] ?? "🏳️",
    club,
    age,
    majors,
    champs,
    top20,
    position,
    grade,
    attrs,
    value,
  };
}

export const PLAYERS: Player[] = DEFS.map(buildPlayer);
export const PLAYER_MAP: Record<string, Player> = Object.fromEntries(PLAYERS.map((p) => [p.id, p]));
