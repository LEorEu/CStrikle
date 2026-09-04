/**
 * 后端 JSON 的形状。**这里只有类型,没有一行玩法逻辑。**
 *
 * 每个字段都对应 Python 那边一个已经算好的值:`/api/draft` 来自
 * `bdserver/draft.py`,`/api/run` 来自 `blinddraft/engine/run.py`。
 * 前端不重算、不推导、不补默认值——缺字段说明后端改了,应该让它报错,
 * 而不是在这里悄悄兜住。
 */

export type Position = "RIFLER" | "AWPER" | "IGL";

/** 盲选期能看见的一张牌。真值(page/昵称/档位/四维)后端不下发。 */
export interface BoardCard {
  index: number;
  price: number;
  position: Position;
  country: string;
  flag: string;
  /** 这个位置真正值得观察的那一维,只给区间 */
  scout: { attr: string; label: string; lo: number; hi: number };
  /** 俱乐部 / Major x N / 年龄,三选一 */
  clue: string;
}

export interface Blueprint {
  tag: string;
  note: string;
  done: boolean;
}

/** `POST /api/draft` 的返回:一局盲选在某一个市场日的全部可见状态。 */
export interface DraftState {
  seed: number;
  actions: number[];
  turn: number;
  turns: number;
  budget: number;
  left: number;
  spent: number;
  slots: number;
  slots_left: number;
  /** 本轮标价上限:后面每个空位至少留 $1 */
  max_price: number;
  can_pass: boolean;
  passes_left: number;
  passed: number[];
  /** 还缺的位置。缺 AWP 扣分,缺 IGL 拿不到战术执行分 */
  missing: Position[];
  board: BoardCard[];
  owned: BoardCard[];
  blueprints: Blueprint[];
  done: boolean;
  /** 只在签满五人后出现,拿它去调 /api/run */
  pages?: string[];
}

/** 揭晓后的完整卡面。顺序和 `DraftState.owned` 一一对应。 */
export interface RosterCard {
  page: string;
  nickname: string;
  position: Position;
  grade: number;
  country: string;
  team: string | null;
  age: number | null;
  firepower: number;
  leadership: number;
  experience: number;
  stability: number;
  /** 相对路径，前端拼 /img/。身份翻开之后才有——盲选那条 API 一张都不发 */
  photo: string;
  flag: string;
}

/** 一个人在一张图上的火力账本(§8 的逐人归因)。 */
export interface Roll {
  nickname: string;
  position: Position;
  side: "player" | "opponent";
  base_firepower: number;
  effective_firepower: number;
  /** 相对卡面的净变化,等于 why 三项之和 */
  delta: number;
  carry_weight: number;
  why: { form: number; pressure: number; soft_capped: number };
}

/** 一张图。引擎只算到这一层——**没有逐回合数据**。 */
export interface MapRow {
  number: number;
  player_strength: number;
  opponent_strength: number;
  player_won: boolean;
  /** 引擎没展开模拟的那部分(地图/经济/timing)的随机 */
  residual: number;
  /** 双方表现差 + residual,正者胜。量纲同 Entry(≈80 那把尺子) */
  margin: number;
  player_fire: number;
  opponent_fire: number;
  player_tactical: number;
  opponent_tactical: number;
  player_structure: number;
  opponent_structure: number;
  player_choke: number;
  opponent_choke: number;
  mvp: Roll;
  life_game: Roll | null;
  underperform: Roll | null;
  players: Roll[];
  opponents: Roll[];
}

export interface Leg {
  label: string;
  stage: number;
  round: number;
  bo: number;
  pressure: number;
  opponent: { name: string; entry: number; vrs: number | null; stage: number };
  won: boolean;
  player_maps: number;
  opponent_maps: number;
  maps: MapRow[];
}

export interface StageRow {
  stage: number;
  wins: number;
  losses: number;
  advanced: boolean;
}

/** `POST /api/run` 的返回:玩家的一整届。 */
export interface RunResult {
  seed: number;
  snapshot: string;
  /** 纯火力口径的队伍强度(≈80),和比赛读的是同一个数 */
  entry: number;
  roster: RosterCard[];
  /** 0 = 没进正赛;1/2/3 = 从第几段瑞士轮打起 */
  stage: number;
  qualified: boolean;
  entry_rank: number;
  demoted: { team: string; from_stage: number; to_stage: number }[];
  dropped: string | null;
  outcome: "not_qualified" | "eliminated" | "playoffs";
  wins: number;
  losses: number;
  reached_playoffs: boolean;
  stages: StageRow[];
  legs: Leg[];
}
