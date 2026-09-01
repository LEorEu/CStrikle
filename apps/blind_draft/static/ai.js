/* AI 对手页 —— 只读。
 *
 * 一行一个人，三组数并排：
 *   卡面   生涯巅峰，玩家抽到的那张（blinddraft/cards.py）
 *   现况   AI 实际用的 = 卡面 经 位置改判 + 年龄衰减（blinddraft/ai_teams.py）
 *   5E     近 12 个月的实测竞技数据（bdtools/fetch_5e_stats.py）
 *
 * 第三组将来要取代第二组里“年龄衰减”那一段。摆在一起是为了让那套映射有得可看：
 * 现在“现况”里的每一分下降都来自一条手拖的曲线，右边那几列才是证据。
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
  $('#mRho').textContent = 'ρ ' + DATA.rho;
  $('#mCov').textContent = '5E 覆盖 ' + c.with_stats + '/' + c.total;
  $('#mAsof').textContent = 'HLTV ' + DATA.asof;

  const noSnap = DATA.teams.filter((t) => !t.in_5e).map((t) => t.name);
  $('#banner').innerHTML = `
    <div>赛场按 <b>HLTV 世界排名（${esc(DATA.asof)}）</b>取前 32 支能凑齐的队，
      阵容与位置来自 <b>5eplay 快照（${esc(DATA.snapshot_date)}）</b>，
      实测数据窗口 <b>${esc((DATA.stats_window || '').replace('_', ' → '))}</b>
      · ${esc(DATA.stats_grade)}。默契上限 ${DATA.cap}。</div>
    <div>年龄衰减 <b>loss = ${DATA.age_curve.rate} × (岁 − ${DATA.age_curve.knee})<sup>${DATA.age_curve.exp}</sup></b>
      ——这条曲线是拖出来的，不是查出来的；右边的 5E 三列就是用来取代它的证据。
      我们的 entry 顺位与 HLTV 排名秩相关 <b>ρ = ${DATA.rho}</b>。</div>
    ${noSnap.length ? `<div class="warn">${noSnap.length} 支队不在 5eplay 快照里（${
      noSnap.map(esc).join('、')}）：两份数据差着好几周，不是名字没配上——它们没有队标和阵容来源。</div>` : ''}`;
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
  const key = { our: (t) => t.our, hltv: (t) => t.hltv, delta: (t) => -Math.abs(t.delta) };
  return out.sort((a, b) => key[by](a) - key[by](b));
}

function teamHead(t) {
  const d = t.delta;
  const dTxt = d === 0 ? '<span class="dim">±0</span>'
    : `<span class="${d > 0 ? 'delta-up' : 'delta-dn'}">${d > 0 ? '+' : ''}${d}</span>`;
  const tags = [
    t.real < 5 ? `<span class="tag warn">补 ${5 - t.real} 人</span>` : '',
    t.adjust ? `<span class="tag acc">人工 ${t.adjust > 0 ? '+' : ''}${t.adjust}</span>` : '',
    t.source !== '当前名单' ? `<span class="tag">${esc(t.source)}</span>` : '',
    t.in_5e ? '' : '<span class="tag warn">不在 5E 快照</span>',
  ].join('');
  const sub = [t.region, t.vrs ? '区内 VRS #' + t.vrs : ''].filter(Boolean).join(' · ');
  const num = (v, label) => `<div class="num"><span class="v">${v}</span><small>${label}</small></div>`;
  return `<div class="team-head">
    <div class="pos">${t.our}</div>
    <div>${t.logo ? `<img class="logo" loading="lazy" src="${esc(t.logo)}">` : ''}</div>
    <div>
      <div class="nm">${esc(t.name)}${tags}</div>
      <div class="sub2">${esc(sub || '—')}</div>
    </div>
    ${num(t.entry, 'entry')}
    ${num(t.cohesion, t.chem > t.cohesion ? `默契 · 原始 ${t.chem}` : '默契')}
    ${num('#' + t.hltv, 'HLTV')}
    ${num(dTxt, '顺位分歧')}
    <div class="lineup">${t.roster.map((p) => esc(p.nickname)).join(' · ')}</div>
  </div>`;
}

function playerRow(p) {
  const card = p.card, cur = p.cur, s = p.stat;
  // 现况这一列按“比卡面高了还是低了”着色——每一分差都来自位置改判或年龄曲线，
  // 而那条曲线正是这一页想让人盯着看的东西。
  const cell = (k, extra) => {
    const cls = ['gB', extra || '', card && cur[k] < card[k] ? 'down'
                                  : card && cur[k] > card[k] ? 'up' : ''].join(' ').trim();
    return `<td class="${cls}">${cur[k]}</td>`;
  };
  const A = (v, extra) => `<td class="gA ${extra || ''}">${v}</td>`;
  const Cc = (v, extra) => `<td class="gC ${extra || ''}">${v}</td>`;
  return `<tr class="${p.filler ? 'filler' : ''}">
    <td class="l">${p.photo ? `<img class="face2" loading="lazy" src="${esc(p.photo)}">`
                            : '<div class="face2"></div>'}</td>
    <td class="l"><div class="pname">
      ${p.flag ? `<img class="flag" loading="lazy" src="${esc(p.flag)}">` : ''}
      <span>${esc(p.nickname)}</span></div></td>
    <td class="l dim">${POS_CN[p.position] || p.position}</td>
    <td><span class="g g${p.grade}">${p.grade}</span></td>
    <td class="dim">${p.age == null ? '—' : p.age}</td>

    ${card ? A(card.firepower, 'sep') + A(card.leadership) + A(card.experience)
             + A(card.stability) + A(card.overall)
           : A('—', 'sep na') + A('—', 'na') + A('—', 'na') + A('—', 'na') + A('—', 'na')}

    ${cell('firepower', 'sep')}${cell('leadership')}${cell('experience')}${cell('stability')}
    <td class="gB"><b>${Number(cur.overall).toFixed(1)}</b></td>

    ${s ? Cc(n2(s.rating), 'sep') + Cc(n1(s.adr)) + Cc(n1(s.kast)) + Cc(n2(s.kd))
          + Cc(n2(s.kpr)) + Cc(n2(s.dpr)) + Cc(n1(s.hs_rate))
          + Cc(s.maps == null ? '—' : s.maps, 'dim') + Cc(esc(s.tier), 'dim')
        : `<td class="gC sep na" colspan="9">${p.filler ? '占位新秀，卡库和 5E 都没有他'
                                                        : '5E 没有这个人的样本'}</td>`}

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

  $('#skipped').innerHTML = DATA.skipped.length ? `
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
