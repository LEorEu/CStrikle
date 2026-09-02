/* 打锚台的前端。
 *
 * 一行两个输入,回答的是两个不同的问题——这一点在 UI 上必须看得出来,
 * 否则会被当成一件事填:
 *
 *   巅峰?    他**现在**是不是处于生涯巅峰。只有「是」的人,他的近 12 个月
 *            rating 才能当作「这个火力值对应的实测水平」,才进右边那张散点图。
 *   火力     他**巅峰时**的火力。对巅峰中的人两者重合,对别人是纯履历判断。
 *
 * 每次改动立刻 PUT,不做「保存」按钮:打 40 个锚是连续的判断流,
 * 中途丢一次就得重来。
 */
'use strict';

const $ = (s, r) => (r || document).querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const n1 = (v) => (v == null ? '—' : Number(v).toFixed(1));
const n2 = (v) => (v == null ? '—' : Number(v).toFixed(2));

let DATA = null;
let TOKEN = localStorage.getItem('bdToken') || '';

function toast(msg, bad) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'on' + (bad ? ' bad' : '');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { t.className = ''; }, bad ? 4000 : 1600);
}

function bandOf(fire) {
  if (fire == null || !DATA) return '';
  for (const [lo, label] of DATA.bands) if (fire >= lo) return label;
  return '';
}

/* ------------------------------------------------------------------ 载入 */
async function load() {
  const teams = $('#teams').value;
  const r = await fetch('/api/anchor?teams=' + teams);
  DATA = await r.json();
  render();
}

function render() {
  const c = DATA.counts;
  $('#mDone').innerHTML = '已打 <b>' + c.anchored + '</b> / ' + c.players;
  $('#mFit').innerHTML = '进拟合 <b>' + c.in_fit + '</b>';
  $('#mSnap').textContent = '快照 ' + (DATA.snapshot_date || '');
  $('#banner').innerHTML =
    '这一页<b>写人工层</b>（<code>firepower_anchors.json</code>），不碰任何生成物。'
    + '两栏分开填：<b>巅峰?</b> 问的是「他现在是否处于生涯巅峰」，'
    + '<b>火力</b> 问的是「他巅峰时该是多少」——'
    + '只有勾了巅峰的人才进右边那张图，因为只有他们的当前 rating 能代表巅峰。'
    + '<br>建议值是一条<b>提示折线</b>，不是结论；点一下就填进去，随便改。'
    + '指挥不给建议值——实测 rating 对指挥的火力没有信号。';

  $('#list').innerHTML = DATA.teams.map(teamHTML).join('');
  bind();
  drawPlot();
  drawLadder();
}

function teamHTML(t) {
  return `<div class="team">
    <h3>${esc(t.name)} <small>全球 VRS #${t.vrs} · ${esc(t.region || '')}</small></h3>
    <table>
      <colgroup>
        <col class="c-nick"><col class="c-role"><col class="c-age">
        <col class="c-num"><col class="c-num"><col class="c-num"><col class="c-num"><col class="c-num">
        <col class="c-grade"><col class="c-fire">
        <col class="c-peak"><col class="c-hint"><col class="c-in"><col class="c-band"><col class="c-note">
      </colgroup>
      <thead><tr>
        <th class="l">选手</th><th class="l">位置</th><th>岁</th>
        <th class="grp">rating</th><th>图</th><th>ADR</th><th>KAST</th><th>K/D</th>
        <th class="grp">档</th><th>卡面火力</th>
        <th class="grp">巅峰?</th><th>建议</th><th>火力</th><th class="l">档位语义</th>
        <th class="l">理由</th>
      </tr></thead>
      <tbody>${t.roster.map(rowHTML).join('')}</tbody>
    </table>
  </div>`;
}

function rowHTML(p) {
  // 图数少的证据要看得出来软:20 图以下的 rating 抖得厉害,不该当硬数据用
  const weak = p.maps < 20 ? ' weak' : '';
  const peakLbl = p.peak === true ? '是' : p.peak === false ? '否' : '—';
  const peakV = p.peak === true ? 'yes' : p.peak === false ? 'no' : '';
  return `<tr data-key="${esc(p.key)}" class="${p.fire != null ? 'done' : ''}">
    <td class="l"><span class="seat">${p.seat || ''}</span> <span class="nick">${esc(p.nickname)}</span></td>
    <td class="l role">${esc(p.role || '')}</td>
    <td class="dim">${p.age == null ? '—' : p.age}</td>
    <td class="grp ev${weak}"><b>${n2(p.rating)}</b></td>
    <td class="ev${weak}">${p.maps || '—'}</td>
    <td class="ev${weak}">${n1(p.adr)}</td>
    <td class="ev${weak}">${n1(p.kast)}</td>
    <td class="ev${weak}">${n2(p.kd)}</td>
    <td class="grp dim">${p.grade == null ? '—' : 'G' + p.grade}</td>
    <td class="card-fire">${p.card_fire == null ? '—' : p.card_fire}</td>
    <td class="grp"><button class="peak-btn" data-v="${peakV}">${peakLbl}</button></td>
    <td class="hintv">${p.hint == null ? '<span class="dim">—</span>'
                                       : '<b class="use">' + p.hint + '</b>'}</td>
    <td><input class="fire${p.fire != null ? ' set' : ''}" type="number" min="1" max="99"
               value="${p.fire == null ? '' : p.fire}" placeholder="—"></td>
    <td class="l band">${esc(bandOf(p.fire))}</td>
    <td class="l"><input class="note" value="${esc(p.note || '')}" placeholder="为什么是这个数"></td>
  </tr>`;
}

/* ------------------------------------------------------------------ 写入 */
function findPlayer(key) {
  for (const t of DATA.teams) for (const p of t.roster) if (p.key === key) return p;
  return null;
}

async function save(tr) {
  const key = tr.dataset.key;
  const p = findPlayer(key);
  if (!p) return;
  const v = $('.peak-btn', tr).dataset.v;
  const fireRaw = $('input.fire', tr).value.trim();
  p.peak = v === 'yes' ? true : v === 'no' ? false : null;
  p.fire = fireRaw === '' ? null : Math.max(1, Math.min(99, Number(fireRaw)));
  p.note = $('input.note', tr).value;

  const r = await fetch('/api/anchor/' + encodeURIComponent(key), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Token': TOKEN },
    body: JSON.stringify({ peak: p.peak, firepower: p.fire, note: p.note,
                           teams: Number($('#teams').value) }),
  });
  if (!r.ok) {
    const detail = await r.text();
    toast('没保存上：' + detail.slice(0, 80), true);
    return;
  }
  const out = await r.json();
  DATA.counts = out.counts;
  tr.classList.toggle('done', p.fire != null);
  $('.band', tr).textContent = bandOf(p.fire);
  $('input.fire', tr).classList.toggle('set', p.fire != null);
  $('#mDone').innerHTML = '已打 <b>' + out.counts.anchored + '</b> / ' + out.counts.players;
  $('#mFit').innerHTML = '进拟合 <b>' + out.counts.in_fit + '</b>';
  drawPlot();
  drawLadder();
  toast(p.nickname + ' 已存');
}

function bind() {
  $('#list').addEventListener('click', (e) => {
    const btn = e.target.closest('.peak-btn');
    if (btn) {
      const order = { '': 'yes', yes: 'no', no: '' };
      const next = order[btn.dataset.v];
      btn.dataset.v = next;
      btn.textContent = next === 'yes' ? '是' : next === 'no' ? '否' : '—';
      save(btn.closest('tr'));
      return;
    }
    const use = e.target.closest('.hintv b.use');
    if (use) {
      const tr = use.closest('tr');
      $('input.fire', tr).value = use.textContent;
      save(tr);
    }
  });
  $('#list').addEventListener('change', (e) => {
    if (e.target.matches('input.fire, input.note')) save(e.target.closest('tr'));
  });
}

/* ------------------------------------------------------------------ 图 */
function drawPlot() {
  const cv = $('#plot');
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth || 360;
  const h = 300;
  cv.width = w * dpr; cv.height = h * dpr; cv.style.height = h + 'px';
  const x = cv.getContext('2d');
  x.setTransform(dpr, 0, 0, dpr, 0, 0);
  x.clearRect(0, 0, w, h);

  const pad = { l: 34, r: 12, t: 12, b: 26 };
  const X0 = 0.80, X1 = 1.50, Y0 = 40, Y1 = 100;
  const sx = (v) => pad.l + (v - X0) / (X1 - X0) * (w - pad.l - pad.r);
  const sy = (v) => h - pad.b - (v - Y0) / (Y1 - Y0) * (h - pad.t - pad.b);
  const css = (k) => getComputedStyle(document.documentElement).getPropertyValue(k).trim();

  x.strokeStyle = css('--line'); x.fillStyle = css('--dim');
  x.font = '10px ui-monospace, monospace'; x.textBaseline = 'middle';
  for (let v = 40; v <= 100; v += 10) {
    x.beginPath(); x.moveTo(pad.l, sy(v) + 0.5); x.lineTo(w - pad.r, sy(v) + 0.5); x.stroke();
    x.textAlign = 'right'; x.fillText(String(v), pad.l - 6, sy(v));
  }
  x.textAlign = 'center';
  for (let v = 0.9; v <= 1.45; v += 0.1) x.fillText(v.toFixed(1), sx(v), h - pad.b + 11);

  // 提示折线:填数时的参照,不是拟合结果
  x.strokeStyle = css('--line'); x.setLineDash([4, 3]); x.lineWidth = 1.5;
  x.beginPath();
  DATA.hint.forEach(([r, f], i) => {
    const px = sx(r), py = sy(Math.max(Y0, Math.min(Y1, f)));
    if (i === 0) x.moveTo(px, py); else x.lineTo(px, py);
  });
  x.stroke(); x.setLineDash([]);

  const pts = DATA.fit;
  if (!pts.length) {
    x.fillStyle = css('--dim'); x.textAlign = 'center';
    x.fillText('还没有勾「巅峰」的锚点', w / 2, h / 2);
    return;
  }
  pts.forEach((p) => {
    const px = sx(p.rating), py = sy(p.fire);
    x.beginPath(); x.arc(px, py, 3 + Math.min(3, p.maps / 80), 0, 6.2832);
    x.fillStyle = css('--acc'); x.fill();
    x.fillStyle = css('--fg'); x.textAlign = 'left'; x.font = '10px system-ui';
    x.fillText(p.nickname, px + 7, py);
    x.font = '10px ui-monospace, monospace';
  });
}

function drawLadder() {
  // 标尺是打锚的**输出**:这里数的是你已经填出来的分布,不是预设的档位
  const counts = new Map(DATA.bands.map(([lo]) => [lo, []]));
  for (const t of DATA.teams) {
    for (const p of t.roster) {
      if (p.fire == null) continue;
      for (const [lo] of DATA.bands) if (p.fire >= lo) { counts.get(lo).push(p.nickname); break; }
    }
  }
  $('#ladder').innerHTML = '<h2 style="margin:14px 0 6px;font-size:14px">标尺现状</h2>'
    + '<p class="hint" style="margin:0 0 8px">这是你已经打出来的分布，不是预设档位。</p>'
    + DATA.bands.map(([lo, label]) => {
      const who = counts.get(lo);
      return `<div class="row${who.length ? '' : ' empty'}">
        <span class="fp">${lo === 0 ? '&lt;52' : lo + '+'}</span>
        <span class="lb">${esc(label)}</span>
        <span class="ct">${who.length ? who.length + ' 人 · ' + esc(who.slice(0, 3).join(' ')) : '空'}</span>
      </div>`;
    }).join('');
}

/* ------------------------------------------------------------------ 起 */
$('#reload').addEventListener('click', load);
$('#teams').addEventListener('change', load);
window.addEventListener('resize', () => { if (DATA) drawPlot(); });
load();
