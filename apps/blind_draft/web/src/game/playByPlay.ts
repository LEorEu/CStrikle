/**
 * 表演层:把后端给的**一张图的结果**摊开成一条回合流水和一份 K/D。
 *
 * ## 这里算的东西不算数
 *
 * 引擎只算到每图(`player_won` / `margin` / 每人 `effective_firepower`),
 * 逐回合和 K/D 后端没有,也不打算有(回合引擎的设计稿在 docs 的 future/,
 * 明确没接)。所以这一层是**演绎**:
 *
 * - 比分必须收敛到 `map.player_won`——谁赢由后端定,这里只决定输的一方拿到
 *   几个回合;
 * - K/D 按后端给的 carry 权重和有效火力分配,总数对得上比分;
 * - 它**不参与任何判定**,也不许反过来影响任何数字。删掉这个文件,比赛结果
 *   一分都不会变。
 *
 * 同一张图必须每次画出同一条流水,否则重渲染会让比分自己跳。所以随机数由
 * `(seed, leg, map)` 起子,不用 Math.random。
 */
import type { MapRow, Roll } from "../api/types";

export interface DerivedRound {
  n: number;
  playerWon: boolean;
  playerScore: number;
  opponentScore: number;
  event: string;
}

export interface DerivedStat {
  nickname: string;
  position: string;
  kills: number;
  deaths: number;
}

export interface DerivedMap {
  playerScore: number;
  opponentScore: number;
  rounds: DerivedRound[];
  playerStats: DerivedStat[];
  opponentStats: DerivedStat[];
}

/** MR12:先到 13 局。这里不做加时,所以输的一方最多 11。 */
const WIN_AT = 13;
const MAX_LOSER = 11;

/** 一个回合里,赢的一方平均拿几个人头 / 输的一方平均拿几个。 */
const KILLS_ON_WIN = 4.3;
const KILLS_ON_LOSS = 1.9;

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 按权重把一个整数总量分下去,四舍五入的零头给余数最大的人,保证加起来正好。 */
function distribute(total: number, weights: number[]): number[] {
  const sum = weights.reduce((s, w) => s + w, 0) || 1;
  const exact = weights.map((w) => (w / sum) * total);
  const out = exact.map((x) => Math.floor(x));
  const rest = total - out.reduce((s, x) => s + x, 0);
  const order = exact
    .map((x, i) => ({ i, frac: x - Math.floor(x) }))
    .sort((a, b) => b.frac - a.frac);
  for (let k = 0; k < rest; k++) out[order[k % order.length].i]++;
  return out;
}

const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / (xs.length || 1);

/**
 * 从 carry 权重和有效火力推一个「这一张图谁在开枪」的权重。
 *
 * `carry_weight` 是**对队伍强度的影响**(.35/.25/其余平摊),不是击杀占比。
 * 直接拿它当权重会把第一枪推到全队 39% 的人头,而现实里顶级 carry 也就
 * 25~30%。`FRAG_FLOOR` 就是那层地板:每个人先有一份基本盘,再按权重拉开。
 */
const FRAG_FLOOR = 0.2;

function fragWeights(rolls: Roll[]): number[] {
  const avg = mean(rolls.map((r) => r.effective_firepower)) || 1;
  return rolls.map((r) => (r.carry_weight + FRAG_FLOOR) * (r.effective_firepower / avg));
}

const WIN_LINES = [
  "%s 开重要的第一枪,回合直接打崩",
  "%s 残局 1v2 收掉",
  "%s 架点架穿,进攻方硬吃",
  "%s 一个 timing 抢到,人数直接拉开",
  "%s 拆包成功,%o 拉不回来",
  "%s 打赢关键的架枪对拉",
];

const LOSS_LINES = [
  "%s 被 %o 单点带走,回合没起来",
  "%s 这枪没打进,道具也跟着废了",
  "%s 被抓了个 timing,人数落后",
  "%s 残局没守住,%o 拿下",
];

function line(pool: string[], hero: string, foil: string, rng: () => number) {
  return pool[Math.floor(rng() * pool.length)]
    .replace("%s", hero)
    .replace("%o", foil);
}

function weightedPick(rolls: Roll[], weights: number[], rng: () => number): Roll {
  const total = weights.reduce((s, w) => s + w, 0);
  let x = rng() * total;
  for (let i = 0; i < rolls.length; i++) {
    x -= weights[i];
    if (x <= 0) return rolls[i];
  }
  return rolls[rolls.length - 1];
}

/**
 * 一张图 -> 一条流水。`key` 只用来起随机数,不影响任何结果字段。
 */
export function deriveMap(map: MapRow, key: number): DerivedMap {
  const rng = mulberry32(key * 7919 + map.number * 104729);

  // 输的一方拿几个回合:分差越大给得越少。margin 是 Entry 那把尺子上的数,
  // 这里只是把它映射成一个看得过去的比分——**它不反过来说明任何事**。
  //
  // 斜率按实测的 margin 分布定的(20 局 148 张图):|margin| 中位数 11.2、
  // p75 17.4、p90 23.3、最大 41.6。所以 0.32 把中位数那张图放在 13-8,
  // p90 落在 13-4,极端分差撞到 13-2 的地板。斜率调大会让绝大多数图看起来
  // 都是屠杀,那和引擎给的分差分布对不上。
  const spread = Math.abs(map.margin);
  const jitter = rng() * 2 - 1;
  const loser = Math.min(MAX_LOSER, Math.max(2, Math.round(11.5 - spread * 0.32 + jitter)));
  const playerScore = map.player_won ? WIN_AT : loser;
  const opponentScore = map.player_won ? loser : WIN_AT;

  // 回合顺序:赢家正好在最后一回合拿到第 13 分,前面随机穿插。
  const flags: boolean[] = [
    ...Array(playerScore - (map.player_won ? 1 : 0)).fill(true),
    ...Array(opponentScore - (map.player_won ? 0 : 1)).fill(false),
  ];
  for (let i = flags.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [flags[i], flags[j]] = [flags[j], flags[i]];
  }
  flags.push(map.player_won);

  const pw = fragWeights(map.players);
  const ow = fragWeights(map.opponents);
  const rounds: DerivedRound[] = [];
  let ps = 0;
  let os = 0;
  flags.forEach((won, i) => {
    won ? ps++ : os++;
    // 主语必须和「谁赢了这一回合」对得上:hero 一定来自赢的那一边。
    // 两个句式的区别只是从谁的角度说这件事——赢的人做成了什么,还是输的人
    // 没做成什么——所以 LOSS_LINES 的主语是 foil,不是 hero。
    const hero = weightedPick(won ? map.players : map.opponents, won ? pw : ow, rng);
    const foil = weightedPick(won ? map.opponents : map.players, won ? ow : pw, rng);
    rounds.push({
      n: i + 1,
      playerWon: won,
      playerScore: ps,
      opponentScore: os,
      event:
        rng() < 0.65
          ? line(WIN_LINES, hero.nickname, foil.nickname, rng)
          : line(LOSS_LINES, foil.nickname, hero.nickname, rng),
    });
  });

  // 有名有姓的三件事来自后端(§0.5 的 MVP / LIFE GAME / 失常),不是这里编的,
  // 所以把它们钉在流水的固定位置上,别让随机文案盖掉。
  if (map.life_game) {
    const at = Math.min(rounds.length - 2, Math.floor(rounds.length * 0.45));
    rounds[at].event = `${map.life_game.nickname} 这一局完全打疯了(+${map.life_game.delta.toFixed(1)} 火力)`;
  }
  if (map.underperform) {
    const at = Math.min(rounds.length - 3, Math.floor(rounds.length * 0.7));
    if (at > 0) rounds[at].event = `${map.underperform.nickname} 又没打出来(${map.underperform.delta.toFixed(1)} 火力)`;
  }
  rounds[rounds.length - 1].event = `${map.mvp.nickname} 结束这张图`;

  // A 队的击杀就是 B 队的死亡,所以两边只算一次。
  const playerKills = Math.round(KILLS_ON_WIN * playerScore + KILLS_ON_LOSS * opponentScore);
  const opponentKills = Math.round(KILLS_ON_WIN * opponentScore + KILLS_ON_LOSS * playerScore);
  const stats = (rolls: Roll[], kills: number, deaths: number): DerivedStat[] => {
    const w = fragWeights(rolls);
    const avg = mean(rolls.map((r) => r.effective_firepower)) || 1;
    // 死亡分得比击杀平均得多:火力高的人少死一点,但不夸张。
    const dw = rolls.map((r) => 1 - 0.25 * ((r.effective_firepower - avg) / avg));
    const k = distribute(kills, w);
    const d = distribute(deaths, dw);
    return rolls.map((r, i) => ({
      nickname: r.nickname,
      position: r.position,
      kills: k[i],
      deaths: d[i],
    }));
  };

  return {
    playerScore,
    opponentScore,
    rounds,
    playerStats: stats(map.players, playerKills, opponentKills),
    opponentStats: stats(map.opponents, opponentKills, playerKills),
  };
}
