export type Position = "IGL" | "AWPER" | "RIFLER";
export type Grade = 1 | 2 | 3 | 4 | 5;
export type Price = 1 | 2 | 3 | 4 | 5;
export type ClueType = "country" | "club" | "age" | "majors" | "champs";

export interface Attributes {
  firepower: number;
  leadership: number;
  experience: number;
  stability: number;
}

export interface Player {
  id: string;
  nick: string;
  country: string;
  flag: string;
  club: string;
  age: number;
  majors: number;
  champs: number;
  top20: number[]; // list of placings in yearly top20 (e.g. [3, 7])
  position: Position;
  grade: Grade;
  attrs: Attributes;
  value: number; // internal weighted value 0-99
}

export interface DraftCard {
  id: string;
  player: Player;
  price: Price;
  clueType: ClueType;
  clueText: string;
  round: number;
}

export interface SignedCard extends DraftCard {
  pickedRound: number;
}

export type ValueTag = "STEAL" | "FAIR" | "OVERPAY";

export interface Buff {
  id: string;
  name: string;
  cost: number;
  desc: string;
  icon: string;
  apply: (t: TeamStats, roster: Player[]) => TeamStats;
}

export interface Trait {
  id: string;
  name: string;
  desc: string;
  tone: "good" | "bad" | "neutral";
  apply: (t: TeamStats) => TeamStats;
}

export interface TeamStats {
  firepower: number;
  tactics: number;
  consistency: number;
  experience: number;
  chemistry: number;
  clutch: number;
  mapBonus: Record<string, number>;
}

export interface OpponentTeam {
  id: string;
  name: string;
  tag: string;
  region: string;
  color: string;
  rating: number;
  consistency: number;
  players: string[];
}

export interface PlayerMapStat {
  id: string;
  nick: string;
  kills: number;
  deaths: number;
}

export interface RoundResult {
  n: number;
  winner: "home" | "away";
  homeScore: number;
  awayScore: number;
  event: string;
}

export interface MapResult {
  map: string;
  homeScore: number;
  awayScore: number;
  winner: "home" | "away";
  rounds: RoundResult[];
  homeStats: PlayerMapStat[];
  awayStats: PlayerMapStat[];
}

export interface MatchDef {
  id: string;
  stage: string;
  label: string;
  opponent: OpponentTeam;
  bo: 1 | 3 | 5;
  elimination: boolean;
  advancement: boolean;
}

export interface MatchOutcome {
  def: MatchDef;
  maps: MapResult[];
  homeMaps: number;
  awayMaps: number;
  won: boolean;
}
