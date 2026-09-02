/* AI 对手页 —— 只读。
 *
 * 一行一个人，三组数并排：
 *   卡面   生涯巅峰，玩家抽到的那张（blinddraft/cards.py）
 *   现况   AI 实际用的逐维当前卡；每格带来源和置信度（blinddraft/ai_teams.py）
 *   5E     近 12 个月的实测竞技数据（bdtools/fetch_5e_stats.py）
 *
 * 队伍是**候选池 45 支**：各大区 VRS 前 N，阵容和队内位置直接查队伍快照。
 * 卡库外真人的“卡面”留白，但“现况”可由当前证据 + 透明低置信先验生成；
 * 这不会把他们写进玩家卡库，也不再用匿名 G1 占位替换真人。
 */
'use strict';

const $ = (s) => document.querySelector(s);
const POS_CN = { RIFLER: '步枪', AWPER: '狙击', IGL: '指挥' };
const ATTRS = ['firepower', 'leadership', 'experience', 'stability'];

let DATA = null;
const open = new Set();

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const n1 = (v) => (v == null ? '<span class="na">—</span>' : v.toFixed(1));
const n2 = (v) => (v == null ? '<span class="na">—</span>' : v.toFixed(2));

/* ------------------------------------------------------------------ 载入 */
async function load() {
  DATA = await (await fetch('/api/ai')).json();
  const c = DATA.coverage;
  const inField = DATA.teams.filter((t) => t.stage).length;
  $('#mRho').textContent = 'ρ ' + DATA.rho;
  $('#mCov').textContent = '5E 覆盖 ' + c.with_stats + '/' + c.total;
  $('#mAsof').textContent = '快照 ' + DATA.snapshot_date;

  const q = DATA.pool || {};
  const quota = ['欧洲', '美洲', '亚洲'].map((k) => {
    const v = (DATA.slots || {})[k];
    return v ? k[0] + ' ' + (v.stage1 + v.stage2 + v.stage3) : '';
  }).filter(Boolean).join(' / ');
  $('#banner').innerHTML = `
    <div>候选池 <b>${DATA.teams.length} 支</b>（欧洲 VRS 前 ${q['欧洲']} · 美洲前 ${q['美洲']} · 亚洲前 ${q['亚洲']}），
      其中 <b>${inField} 支</b>拿到 Major 名额（${esc(quota)}），
      其余 ${DATA.teams.length - inField} 支是留给 VRS 变动的余量。
      阵容与队内位置来自 <b>5eplay 快照（${esc(DATA.snapshot_date)}）</b>，
      实测窗口 <b>${esc((DATA.stats_window || '').replace('_', ' → '))}</b> · ${esc(DATA.stats_grade)}。
      默契上限 ${DATA.cap}。</div>
    <div class="warn"><b>${c.nocard} 人卡库里没有</b>——他们没有玩家卡，但有 AI 专属当前四维；
      当前证据不足的维度会明确标成低置信先验。五人完整的 <b>${DATA.scored} / ${DATA.teams.length}</b>
      支队均可计算预测种子分。</div>
    <div>当前 Firepower：80 图以上直接读标尺，30–79 图向生涯先验收缩；IGL 与无可靠证据者
      才使用年龄/生涯回退。预测顺位与 HLTV 排名秩相关 <b>ρ = ${DATA.rho}</b>，
      它是 Match 的赛前基准，不是官方实力排名。</div>`;
  if (location.hash === '#all') {
    $('#expandAll').checked = true;
    DATA.teams.forEach((t) => open.add(t.name));
  }
  render();
}

/* -------------------------------------------------------------- 队伍列表 */
function sorted() {
  const q = $('#q').value.trim().toLowerCase();
  const by = $('#sort').value;
  let out = DATA.teams.filter((t) => !q || t.name.toLowerCase().includes(q)
    || t.roster.some((p) => p.nickname.toLowerCase().includes(q)));
  const big = 1e6;                       // 缺值一律沉底，不参与比较
  const key = {
    vrs: (t) => t.vrs || big,
    our: (t) => (t.our == null ? big : t.our),
    hltv: (t) => t.hltv || big,
    delta: (t) => (t.delta == null ? big : -Math.abs(t.delta)),
  };
  return out.sort((a, b) => (key[by] || key.vrs)(a) - (key[by] || key.vrs)(b));
}

function teamHead(t) {
  const d = t.delta;
  const dTxt = d == null ? '<span class="na">—</span>'
    : d === 0 ? '<span class="dim">±0</span>'
    : `<span class="${d > 0 ? 'delta-up' : 'delta-dn'}">${d > 0 ? '+' : ''}${d}</span>`;
  const tags = [
    t.real < 5 ? `<span class="tag warn">${5 - t.real} 人卡库里没有</span>` : '',
    t.adjust ? `<span class="tag acc">人工 ${t.adjust > 0 ? '+' : ''}${t.adjust}</span>` : '',
    (t.gaps || []).length ? `<span class="tag warn">缺 ${t.gaps.join('/')}</span>` : '',
    t.evidence ? `<span class="tag">火力证据 ${t.evidence.strong}强/${t.evidence.supporting}弱/${t.evidence.low}先验</span>` : '',
  ].join('');
  // 区内名次才是决定名额的那个数，全球 VRS 只用来排种子。以前这里把全球名次
  // 标成「区内 VRS」，一直是错的。
  const sub = [t.region ? t.region + '区 #' + t.seat : '',
    t.stage ? 'Stage ' + t.stage : '余量',
    t.vrs ? '全球 VRS #' + t.vrs : ''].filter(Boolean).join(' · ');
  const num = (v, label) => `<div class="num"><span class="v">${v}</span><small>${label}</small></div>`;
  return `<div class="team-head${t.stage ? '' : ' reserve'}">
    <div class="pos">${t.our == null ? '<span class="na">·</span>' : t.our}</div>
    <div>${t.logo ? `<img class="logo" loading="lazy" src="${esc(t.logo)}">` : ''}</div>
    <div>
      <div class="nm">${esc(t.name)}${tags}</div>
      <div class="sub2">${esc(sub || '—')}</div>
    </div>
    ${num(t.entry == null ? '<span class="na">—</span>' : t.entry, '预测分')}
    ${num(t.cohesion == null ? '<span class="na">—</span>' : t.cohesion,
          t.chem != null && t.chem > t.cohesion ? `默契 · 原始 ${t.chem}` : '默契')}
    ${num(t.hltv ? '#' + t.hltv : '<span class="na">—</span>', 'HLTV')}
    ${num(dTxt, '顺位分歧')}
    <div class="lineup">${t.roster.map((p) => esc(p.nickname)).join(' · ')}</div>
  </div>`;
}

function playerRow(p) {
  const card = p.card, cur = p.cur, s = p.stat;
  // 现况按“比卡面高了还是低了”着色；悬停可看这一维的来源、置信度和解释。
  const cell = (k, extra) => {
    if (!cur) return `<td class="gB ${extra || ''} na">—</td>`;
    const cls = ['gB', extra || '', card && cur[k] < card[k] ? 'down'
                                  : card && cur[k] > card[k] ? 'up' : ''].join(' ').trim();
    const src = (cur.sources || {})[k] || {};
    const tip = [src.source, src.confidence, src.why].filter(Boolean).join(' · ');
    return `<td class="${cls}" title="${esc(tip)}">${cur[k]}</td>`;
  };
  const A = (v, extra) => `<td class="gA ${extra || ''}">${v}</td>`;
  const Cc = (v, extra) => `<td class="gC ${extra || ''}">${v}</td>`;
  return `<tr class="${p.nocard ? 'nocard' : ''}">
    <td class="l">${p.photo ? `<img class="face2" loading="lazy" src="${esc(p.photo)}">`
                            : '<div class="face2"></div>'}</td>
    <td class="l"><div class="pname">
      ${p.flag ? `<img class="flag" loading="lazy" src="${esc(p.flag)}">` : ''}
      <span>${esc(p.nickname)}</span></div></td>
    <td class="l dim">${POS_CN[p.position] || p.position}${
      p.caller && p.position !== 'IGL' ? '·指挥' : ''}${
      p.role_src ? `<i class="guess" title="位置由竞技数据判定：${esc(p.role_src)}">?</i>` : ''}</td>
    <td>${p.grade == null ? '<span class="na">—</span>'
                          : `<span class="g g${p.grade}">${p.grade}</span>`}</td>
    <td class="dim">${p.age == null ? '—' : p.age}</td>

    ${card ? A(card.firepower, 'sep') + A(card.leadership) + A(card.experience)
             + A(card.stability) + A(card.overall)
           : A('—', 'sep na') + A('—', 'na') + A('—', 'na') + A('—', 'na') + A('—', 'na')}

    ${cell('firepower', 'sep')}${cell('leadership')}${cell('experience')}${cell('stability')}
    <td class="gB">${cur ? `<b>${Number(cur.overall).toFixed(1)}</b>`
                         : '<span class="na">—</span>'}</td>

    ${s ? Cc(n2(s.rating), 'sep') + Cc(n1(s.adr)) + Cc(n1(s.kast)) + Cc(n2(s.kd))
          + Cc(n2(s.kpr)) + Cc(n2(s.dpr)) + Cc(n1(s.hs_rate))
          + Cc(s.maps == null ? '—' : s.maps, 'dim')
          + Cc(esc(s.tier), 'dim')
        : '<td class="gC sep na" colspan="9">这一年没有 Major / S+ / S 级样本</td>'}

    <td class="l note2">${p.notes.map(esc).join('；')}</td>
  </tr>`;
}

function rosterTable(t) {
  return `<div class="roster"><table class="ros">
    <thead>
      <tr>
        <th colspan="5"></th>
        <th class="grp gA sep" colspan="5">卡面 · 生涯巅峰</th>
        <th class="grp gB sep" colspan="5">现况 · AI 实际用的</th>
        <th class="grp gC sep" colspan="9">5E 实测 · 近 12 个月</th>
        <th></th>
      </tr>
      <tr>
        <th></th><th class="l">选手</th><th class="l">位</th><th>档</th><th>岁</th>
        <th class="gA sep">火</th><th class="gA">领</th><th class="gA">经</th>
        <th class="gA">稳</th><th class="gA">OVR</th>
        <th class="gB sep">火</th><th class="gB">领</th><th class="gB">经</th>
        <th class="gB">稳</th><th class="gB">OVR</th>
        <th class="gC sep">rating</th><th class="gC">ADR</th><th class="gC">KAST</th>
        <th class="gC">K/D</th><th class="gC">KPR</th><th class="gC">DPR</th>
        <th class="gC">HS%</th><th class="gC">图数</th><th class="gC">档次</th>
        <th class="l">改动</th>
      </tr>
    </thead>
    <tbody>${t.roster.map(playerRow).join('')}</tbody>
  </table></div>`;
}

function render() {
  const list = sorted();
  $('#count').textContent = list.length + ' 支队';
  $('#teams').innerHTML = list.map((t) => `
    <div class="team ${open.has(t.name) ? 'open' : ''}" data-name="${esc(t.name)}">
      ${teamHead(t)}
      ${open.has(t.name) ? rosterTable(t) : ''}
    </div>`).join('');

  $('#skipped').innerHTML = (DATA.skipped || []).length ? `
    <h4>没进赛场的队（现役队员不足，需要在 major_field.json 里手写阵容）</h4>
    ${DATA.skipped.map((s) =>
      `<span>HLTV #${s.rank} <b>${esc(s.name)}</b> 只有 ${s.have} 人</span>`).join('')}` : '';
}

/* -------------------------------------------------------------------- 绑定 */
$('#q').addEventListener('input', render);
$('#sort').addEventListener('change', render);
$('#expandAll').addEventListener('change', (e) => {
  open.clear();
  if (e.target.checked) DATA.teams.forEach((t) => open.add(t.name));
  render();
});
$('#teams').addEventListener('click', (e) => {
  const box = e.target.closest('.team');
  if (!box) return;
  const name = box.dataset.name;
  open.has(name) ? open.delete(name) : open.add(name);
  render();
});

load().catch((e) => { $('#banner').textContent = '载入失败：' + e.message; });
