/* Blind Draft 卡牌调参台。
 *
 * 页面上不算任何数值:四维、overall、分布统计全部由服务端跑
 * `blinddraft.cards.build_card(trace=True)` 得出。这里只负责显示和提交。
 * 在 JS 里重算一遍公式,就等于让页面显示的数和引擎读的数各算各的——
 * 而这个后台存在的意义正是消灭这种漂移。
 */
'use strict';

const $ = (s) => document.querySelector(s);
const ATTR_CN = { firepower: '火力', leadership: '领导', experience: '经验', stability: '稳定' };
const POS_CN = { RIFLER: '步枪', AWPER: '狙击', IGL: '指挥' };

let DATA = null;          // /api/cards 的完整响应
let CUR = null;           // 当前选中的 page
const token = localStorage.getItem('bdToken') || '';

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function toast(msg, bad) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast' + (bad ? ' bad' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), 2600);
}

async function api(path, opts) {
  const o = Object.assign({ headers: {} }, opts || {});
  o.headers['Content-Type'] = 'application/json';
  if (token) o.headers['X-Admin-Token'] = token;
  const r = await fetch(path, o);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || r.status);
  return body;
}

/* ------------------------------------------------------------------ 载入 */
async function load() {
  DATA = await api('/api/cards');
  DATA.index = {};
  DATA.cards.forEach((c) => { DATA.index[c.page] = c; });
  $('#metaVer').textContent = DATA.card_version;
  $('#metaCount').textContent = DATA.cards.length + ' 张';
  renderStats();
  renderDiff();
  render();
  // 地址栏里的 #<page> 直接选中那张卡,刷新后停在原地,也能把某张卡的链接发给别人。
  const want = CUR || decodeURIComponent(location.hash.slice(1));
  if (want && DATA.index[want]) select(want);
}

function renderStats() {
  const s = DATA.stats;
  const part = (title, obj, label) => {
    const bits = Object.keys(obj).map((k) =>
      `${label(k)} <b>${obj[k].median}</b><span class="dim">/${obj[k].n}</span>`);
    return `<span>${title} ${bits.join(' · ')}</span>`;
  };
  // 中位数在前、张数在后:调参看的是中位数有没有把某一档顶穿,
  // 张数只是提醒这一档的样本有多大。
  $('#stats').innerHTML =
    part('位置中位数', s.position, (k) => POS_CN[k] || k) +
    part('档位中位数', s.grade, (k) => 'G' + k);
}

function renderDiff() {
  const b = $('#btnDiff');
  const n = DATA.diff.length;
  b.classList.toggle('hidden', n === 0);
  b.textContent = `待发布 ${n}`;
}

/* -------------------------------------------------------------- 列表渲染 */
function filtered() {
  const q = $('#q').value.trim().toLowerCase();
  const pos = $('#fPos').value, grade = $('#fGrade').value;
  const onlyOv = $('#fOv').checked, sort = $('#sort').value;
  let out = DATA.cards.filter((c) => {
    if (pos && c.position !== pos) return false;
    if (grade && String(c.grade) !== grade) return false;
    if (onlyOv && !Object.keys(c.override).length) return false;
    if (q) {
      const hay = (c.nickname + ' ' + c.page + ' ' + (c.team || '')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  out.sort(sort === 'nickname'
    ? (a, b) => a.nickname.localeCompare(b.nickname)
    : (a, b) => b[sort] - a[sort]);
  return out;
}

function render() {
  const rows = filtered();
  $('#listCount').textContent = rows.length + ' / ' + DATA.cards.length;
  $('#rows').innerHTML = rows.map((c) => {
    const ov = c.override || {};
    const cell = (k) =>
      `<td class="n${ov[k] !== undefined ? ' ov' : ''}">${c[k]}</td>`;
    return `<tr data-page="${esc(c.page)}"${c.page === CUR ? ' class="on"' : ''}>
      <td>${c.photo ? `<img class="face" loading="lazy" src="/img/${esc(c.photo)}">`
                    : '<div class="face"></div>'}</td>
      <td><div class="who">${c.flag ? `<img class="flag" loading="lazy" src="/img/${esc(c.flag)}">` : ''}
          <span>${esc(c.nickname)}</span>
          ${Object.keys(ov).length ? '<span class="dot" title="有人工覆盖">●</span>' : ''}</div></td>
      <td class="dim">${POS_CN[c.position] || c.position}</td>
      <td><span class="g g${c.grade}">${c.grade}</span></td>
      <td class="dim">${esc(c.team || '—')}</td>
      ${cell('firepower')}${cell('leadership')}${cell('experience')}${cell('stability')}
      <td class="n"><b>${c.overall}</b></td><td></td>
    </tr>`;
  }).join('');
}

/* -------------------------------------------------------------- 详情面板 */
function deriveTable(t) {
  const num = (v, digits) => {
    const s = (digits ? v.toFixed(1) : String(v));
    return v === 0 ? `<td class="zero">${s}</td>` : `<td>${v > 0 && digits ? '+' + s : s}</td>`;
  };
  const rows = Object.keys(ATTR_CN).map((k) => {
    const a = t.attrs[k];
    const hasOv = a.override !== null && a.override !== undefined;
    return `<tr class="${hasOv ? 'has-ov' : ''}">
      <td>${ATTR_CN[k]}</td>
      <td>${a.base}</td>${num(a.delta, 1)}${num(a.jitter, 1)}
      <td class="dim">${a.auto}</td>
      <td>${hasOv ? a.override : '<span class="zero">—</span>'}</td>
      <td class="fin">${a.final}</td>
      <td class="dim">×${t.weight[k]}</td>
    </tr>`;
  }).join('');
  return `<table class="derive">
    <thead><tr><th>维度</th><th>模板</th><th>履历</th><th>抖动</th>
      <th>自动</th><th>人工</th><th>最终</th><th>权重</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function evidenceBlock(c) {
  const e = c._trace.evidence;
  const t20 = e.top20.length
    ? e.top20.map(([y, r]) => `${y}<b> #${r}</b>`).join('、') : '<span class="zero">无</span>';
  const row = (k, v) => `<div class="row"><span>${k}</span><span>${v}</span></div>`;
  const pct = (s, a) => `${s} / ${a} = <b>${Math.min(s / a * 100, 100).toFixed(0)}%</b>`;
  return `<div class="ev">
    ${row('HLTV Top20', t20)}
    ${row('火力履历', pct(e.top20_score, e.fire_anchor) + ' 的档内幅度')}
    ${c.position === 'IGL' ? row('指挥荣誉分', pct(e.igl_score, e.lead_anchor) + ' 的档内幅度') : ''}
    ${row('Major', `${e.majors} 届 · ${e.champions} 冠 · 最好第 ${e.best_placement} 名`)}
    ${row('年龄', e.age == null ? '未知' : e.age + ' 岁')}
    ${row('随机抖动', c._trace.jitter ? '有(证据不足的档)' : '无(G5/G4 证据已足)')}
  </div>`;
}

function select(page) {
  CUR = page;
  if (history.replaceState) history.replaceState(null, '', '#' + encodeURIComponent(page));
  const c = DATA.index[page];
  const t = c._trace, ov = c.override || {};
  const auto = (k) => t.attrs[k].auto;
  const gradeChanged = t.grade.auto !== t.grade.final;
  const posChanged = t.position.auto !== t.position.final;

  $('#panel').innerHTML = `
    <div class="phead">
      ${c.photo ? `<img class="big" src="/img/${esc(c.photo)}">` : '<div class="big"></div>'}
      <div>
        <h3>${esc(c.nickname)}</h3>
        <div class="pmeta">
          ${esc(c.page)}<br>
          ${esc(c.country || '—')} · ${esc(c.team || '无队')} · ${c.age == null ? '?' : c.age} 岁<br>
          <span class="g g${c.grade}">${c.grade}</span>
          ${POS_CN[c.position]}${posChanged ? ` <span class="dot">(自动判 ${POS_CN[t.position.auto]})</span>` : ''}
          ${gradeChanged ? `<span class="dot">(自动判 G${t.grade.auto})</span>` : ''}
          · OVR <b>${c.overall}</b>
        </div>
      </div>
    </div>

    <h4>推导</h4>
    ${deriveTable(t)}

    <h4>证据</h4>
    ${evidenceBlock(c)}

    <h4>人工覆盖</h4>
    <form class="edit" id="edit">
      <div class="grid">
        <div><label>档位</label><select name="grade">
          <option value="">自动 (G${t.grade.auto})</option>
          ${[5, 4, 3, 2, 1].map((g) =>
            `<option value="${g}"${ov.grade === g ? ' selected' : ''}>G${g}</option>`).join('')}
        </select></div>
        <div><label>位置</label><select name="position">
          <option value="">自动 (${POS_CN[t.position.auto]})</option>
          ${['RIFLER', 'AWPER', 'IGL'].map((p) =>
            `<option value="${p}"${ov.position === p ? ' selected' : ''}>${POS_CN[p]}</option>`).join('')}
        </select></div>
        ${Object.keys(ATTR_CN).map((k) => `
        <div><label>${ATTR_CN[k]}</label>
          <input name="${k}" type="number" min="1" max="99"
                 placeholder="自动 ${auto(k)}" value="${ov[k] !== undefined ? ov[k] : ''}"></div>`).join('')}
      </div>
      <div style="margin-top:8px">
        <label>理由 —— 算法哪里算错了</label>
        <textarea name="reason" placeholder="§21 Algorithm First, Override Last：算法明显违背常识才覆盖，不是逐个人工打分">${esc(ov.reason || '')}</textarea>
      </div>
      <div class="actions">
        <button type="submit" class="primary">保存覆盖</button>
        <button type="button" class="danger" id="btnClear"
          ${Object.keys(ov).length ? '' : 'disabled'}>撤销覆盖</button>
      </div>
      <p class="note">改档位或位置等于<b>换整套模板</b>（在四维计算之前生效）；
      四维是算完之后直接替换。空着就走算法。</p>
    </form>`;

  document.querySelectorAll('#rows tr').forEach((tr) =>
    tr.classList.toggle('on', tr.dataset.page === page));
  $('#edit').addEventListener('submit', save);
  $('#btnClear').addEventListener('click', clearOverride);
}

/* ------------------------------------------------------------------ 写入 */
function formBody() {
  const f = $('#edit');
  const val = (n) => f.elements[n].value.trim();
  const num = (n) => (val(n) === '' ? null : Number(val(n)));
  return {
    grade: num('grade'), position: val('position') || null,
    firepower: num('firepower'), leadership: num('leadership'),
    experience: num('experience'), stability: num('stability'),
    reason: val('reason'),
  };
}

async function afterWrite(msg) {
  await load();
  toast(msg);
}

async function save(ev) {
  ev.preventDefault();
  try {
    await api('/api/card/' + encodeURIComponent(CUR),
      { method: 'PUT', body: JSON.stringify(formBody()) });
    await afterWrite('已写入人工层');
  } catch (e) { toast(String(e.message || e), true); }
}

async function clearOverride() {
  try {
    await api('/api/card/' + encodeURIComponent(CUR), { method: 'DELETE' });
    await afterWrite('已撤销');
  } catch (e) { toast(String(e.message || e), true); }
}

async function publish() {
  if (!confirm('把当前实时结果写进 draft_cards.json？\n\n'
    + '这会覆盖已提交的卡库文件，' + DATA.diff.length + ' 张卡发生变化。')) return;
  try {
    const r = await api('/api/publish', { method: 'POST' });
    await afterWrite('已写出 ' + r.count + ' 张');
  } catch (e) { toast(String(e.message || e), true); }
}

/* -------------------------------------------------------------- 待发布 */
function showDiff() {
  const KIND = { added: '新增', removed: '消失', changed: '变化' };
  const LABEL = Object.assign({ grade: '档位', position: '位置', overall: 'OVR' }, ATTR_CN);
  const fmt = (v) => (POS_CN[v] || v);
  const body = DATA.diff.map((d) => `<tr>
    <td class="kind-${d.kind}">${KIND[d.kind]}</td>
    <td>${esc(d.nickname)}</td>
    <td class="dim">${d.why ? esc(d.why) : d.fields.map((f) =>
      `${LABEL[f.key] || f.key} ${fmt(f.was)}→<b>${fmt(f.now)}</b>`).join('　')}</td>
  </tr>`).join('');
  $('#mTitle').textContent = `待发布 ${DATA.diff.length} 张`;
  $('#mBody').innerHTML = `
    <p class="dim">实时重算的结果和已提交的 draft_cards.json 不一致。差异有两种来源：
    刚改过人工层（意料之中），或者选手库在背后被刷新过（意料之外——多打一届
    Major 就可能换档，而卡库文件还停在上一次写出的状态）。</p>
    <table>${body}</table>`;
  $('#modal').classList.remove('hidden');
}

/* -------------------------------------------------------------------- 绑定 */
['q', 'fPos', 'fGrade', 'sort', 'fOv'].forEach((id) => {
  const el = document.getElementById(id);
  el.addEventListener(el.tagName === 'INPUT' && el.type !== 'checkbox' ? 'input' : 'change', render);
});
$('#rows').addEventListener('click', (e) => {
  const tr = e.target.closest('tr');
  if (tr) select(tr.dataset.page);
});
$('#btnDiff').addEventListener('click', showDiff);
$('#btnPublish').addEventListener('click', publish);
$('#mClose').addEventListener('click', () => $('#modal').classList.add('hidden'));

load().catch((e) => toast('载入失败：' + e.message, true));
