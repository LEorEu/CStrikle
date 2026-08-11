/* FribergCS2 frontend */
"use strict";
const $ = (id) => document.getElementById(id);
const API = "";
const STREAMER_MODE_KEY = "cstrikle_streamer_mode";

let META = null, PLAYERS = [];
let soloGame = null;
const guessedPlayerProfiles = new Map();
let profileReturnFocus = null;
let streamerMode = localStorage.getItem(STREAMER_MODE_KEY) === "1";
let streamerReveal = false;
let room = {
  ws: null, code: null, token: null, state: null, vsAi: false,
  chat: [], lastStatus: null,
};

/* ---------------- country flags ---------------- */
const ISO = {
  "Denmark":"DK","Sweden":"SE","Norway":"NO","Finland":"FI","France":"FR","Germany":"DE",
  "Poland":"PL","Czech Republic":"CZ","Czechia":"CZ","Slovakia":"SK","United Kingdom":"GB",
  "Spain":"ES","Portugal":"PT","Netherlands":"NL","Belgium":"BE","Bosnia and Herzegovina":"BA",
  "Serbia":"RS","Croatia":"HR","Slovenia":"SI","Montenegro":"ME","North Macedonia":"MK",
  "Bulgaria":"BG","Romania":"RO","Hungary":"HU","Austria":"AT","Switzerland":"CH","Italy":"IT",
  "Greece":"GR","Turkey":"TR","Türkiye":"TR","Estonia":"EE","Latvia":"LV","Lithuania":"LT",
  "Iceland":"IS","Ireland":"IE","Kosovo":"XK","Albania":"AL","Moldova":"MD","Luxembourg":"LU",
  "Malta":"MT","Russia":"RU","Ukraine":"UA","Belarus":"BY","Kazakhstan":"KZ","Uzbekistan":"UZ",
  "Kyrgyzstan":"KG","Armenia":"AM","Georgia":"GE","Azerbaijan":"AZ","Tajikistan":"TJ",
  "United States":"US","Canada":"CA","Mexico":"MX","Brazil":"BR","Argentina":"AR","Chile":"CL",
  "Uruguay":"UY","Peru":"PE","Colombia":"CO","Venezuela":"VE","Ecuador":"EC","Paraguay":"PY",
  "Bolivia":"BO","Guatemala":"GT","Costa Rica":"CR","Dominican Republic":"DO",
  "China":"CN","Mongolia":"MN","South Korea":"KR","Japan":"JP","Taiwan":"TW","Hong Kong":"HK",
  "Singapore":"SG","Malaysia":"MY","Indonesia":"ID","Thailand":"TH","Vietnam":"VN",
  "Philippines":"PH","India":"IN","Pakistan":"PK","Bangladesh":"BD","Sri Lanka":"LK",
  "Nepal":"NP","Myanmar":"MM","Laos":"LA","Cambodia":"KH","Macau":"MO",
  "Australia":"AU","New Zealand":"NZ","Israel":"IL","Jordan":"JO","Lebanon":"LB",
  "Saudi Arabia":"SA","United Arab Emirates":"AE","Qatar":"QA","Kuwait":"KW","Iraq":"IQ",
  "Iran":"IR","Egypt":"EG","South Africa":"ZA","Morocco":"MA","Tunisia":"TN","Algeria":"DZ",
  "Nigeria":"NG","Kenya":"KE",
};
function flag(country) {
  const iso = ISO[country];
  if (!iso || iso === "XK") return "";
  return [...iso].map(c => String.fromCodePoint(0x1F1E6 + c.charCodeAt(0) - 65)).join("");
}
const REGION_CN = {
  "Europe":"欧洲","CIS":"独联体","North America":"北美","South America":"南美",
  "Asia":"亚洲","Oceania":"大洋洲","Middle East & Africa":"中东非洲","Other":"其他",
};
const cnCountry = (c) => COUNTRY_CN[c] || c || "?";
const ROLE_CN = { "Rifler": "步枪手", "AWPer": "狙击手", "IGL": "指挥",
                  "Coach": "教练", "Analyst": "分析师" };
const cnRole = (r) => ROLE_CN[r] || r || "?";

/* ---------------- infra ---------------- */
function toast(msg, ms = 2600) {
  const t = $("toast");
  t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), ms);
}
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const r = await fetch(API + path, {
    ...opts, headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return r.json();
}
function go(view) {
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  $("view-" + view).classList.remove("hidden");
  // 离开对战大厅(除进房间外)时退出匹配队列,不占等待位
  if (view !== "versus-lobby" && view !== "room" &&
      typeof match !== "undefined" && match.ticket) cancelMatch();
  if (view !== "room" && room.ws) {
    // 离开房间视图 = 明确弃局:先告诉服务端,AI/计时立即停
    const ws = room.ws; room.ws = null;
    if (ws.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify({ type: "leave" })); } catch {}
    }
    ws.close();
  }
}

/* ---------------- 新旧 UI 切换 ---------------- */
const uiV2 = () => document.documentElement.dataset.ui === "v2";
function toggleUi() {
  const next = uiV2() ? "v1" : "v2";
  document.documentElement.dataset.ui = next;
  try { localStorage.setItem("fcs2_ui", next); } catch {}
  // 两张皮肤的地址挂在元素的 data-v1/data-v2 上,服务端已给它们打好版本号
  const link = $("theme-css");
  link.setAttribute("href", next === "v2" ? link.dataset.v2 : link.dataset.v1);
  updateUiToggle();
  // 幽灵弹夹等 v2 专属结构要跟上当前视图
  if (soloGame && !$("view-game").classList.contains("hidden")) renderSolo();
  if (room.state && !$("view-room").classList.contains("hidden")) renderRoom();
}
function updateUiToggle() {
  const b = $("ui-toggle");
  if (!b) return;
  b.textContent = uiV2() ? "经典 UI" : "新版 UI";
  b.title = uiV2() ? "切回经典界面" : "试试新版转播风界面";
}

/* ---------------- settings widget ---------------- */
function renderSettings(container, { withGuesses = true, withTimer = false,
                                     onDifficulty = null } = {}) {
  const el = typeof container === "string" ? $(container) : container;
  const regions = META ? META.regions : [];
  el.innerHTML = `
  <div class="settings">
    <div class="srow"><b>难度</b>
      <span class="seg" data-k="difficulty">
        <button data-v="top20">Top20</button>
        <button data-v="easy">简单</button>
        <button data-v="medium" class="on">常规</button>
        <button data-v="hard">困难</button>
        <button data-v="custom">自定义</button>
      </span>
      <span class="dim pool-hint"></span>
      <button class="qtip" type="button" title="属性判定规则"
        aria-label="展开属性判定规则" aria-expanded="false">?</button>
    </div>
    <div class="srow diff-desc-row"><b></b><span class="dim diff-desc"></span></div>
    <div class="rules-pop hidden">
      <div class="rules-title">
        <span>游戏规则</span>
        <b>属性判定</b>
      </div>
      <div class="rules-grid">
        <section>
          <span class="rule-no">01</span>
          <div><b>位置</b>
            <p>位置分为指挥、狙击手、步枪手和教练。现任主教练按教练计算；助教和其他工作人员按选手时期的位置计算。</p>
          </div>
        </section>
        <section>
          <span class="rule-no">02</span>
          <div><b>混合位置</b>
            <p>指挥狙和狙枪双修在位置格判黄色“有重叠”；指挥默认持步枪，所以指挥与普通步枪手之间不给黄色。</p>
          </div>
        </section>
        <section>
          <span class="rule-no">03</span>
          <div><b>战队 / 自由身</b>
            <p>当前正式阵容选手和现任主教练显示所属战队。退役、无队、下放、替补、助教和其他工作人员显示自由身；加入新队后按新队计算。</p>
          </div>
        </section>
      </div>
      <div class="region-protocol">
        <b>赛区划分</b>
        <div class="region-list">
          <span>欧洲 <small>含土耳其</small></span>
          <span>独联体 <small>含哈萨克斯坦</small></span>
          <span>北美</span><span>南美</span><span>亚洲</span><span>大洋洲</span>
          <span>中东非洲 <small>含以色列</small></span>
        </div>
      </div>
    </div>
    <div class="custom-rows hidden">
      <div class="srow"><b>赛区</b>
        <span class="regions">${regions.map(r =>
          `<span class="tag" data-r="${r}">${REGION_CN[r] || r}</span>`).join("")}</span>
      </div>
      <div class="srow"><b></b><span class="dim">不选 = 全部赛区</span></div>
      <div class="srow"><b>范围</b>
        <label class="chk" style="margin:0"><input type="checkbox" class="active-only">仅现役</label>
      </div>
      <div class="srow"><b>Major年代</b>
        <span class="yr-span">
          <select class="yr-from"><option value="">2013</option>${range(2014, 2026).map(y => `<option>${y}</option>`).join("")}</select>
          —
          <select class="yr-to">${range(2013, 2025).map(y => `<option>${y}</option>`).join("")}<option value="" selected>至今</option></select>
        </span>
      </div>
      ${withGuesses ? `<div class="srow"><b>猜测次数</b>
        <select class="max-guesses"><option>6</option><option selected>8</option><option>10</option><option>12</option></select>
      </div>` : ""}
      ${withTimer ? `<div class="srow"><b>整局限时</b>
        <select class="game-seconds">
          <option value="" selected>不限时</option>
          <option value="60">1 分钟</option>
          <option value="120">2 分钟</option>
          <option value="180">3 分钟</option>
        </select>
      </div>` : ""}
      ${withTimer ? `<div class="srow"><b></b><span class="dim">时间到还没人猜中就算平局</span></div>` : ""}
    </div>
  </div>`;
  const seg = el.querySelector(".seg");
  const hint = el.querySelector(".pool-hint");
  const collect = () => {
    const difficulty = seg.querySelector(".on").dataset.v;
    if (difficulty !== "custom")
      // 标准难度(含 Top20)用固定规则:8 次猜测,对战整局限时 2 分钟
      return { difficulty, regions: [], active_only: false,
               year_from: null, year_to: null, max_guesses: 8,
               game_seconds: withTimer ? 120 : null };
    return {
      difficulty,
      regions: [...el.querySelectorAll(".tag.on")].map(t => t.dataset.r),
      active_only: el.querySelector(".active-only").checked,
      year_from: +el.querySelector(".yr-from").value || null,
      year_to: +el.querySelector(".yr-to").value || null,
      max_guesses: withGuesses ? +el.querySelector(".max-guesses").value : 8,
      game_seconds: withTimer ? (+el.querySelector(".game-seconds").value || null) : null,
    };
  };
  // 任何筛选条件变化都实时刷新候选人数(轻防抖)
  let hintTimer = null;
  const updHint = () => {
    clearTimeout(hintTimer);
    hintTimer = setTimeout(async () => {
      try {
        const d = await api("/api/pool_count", {
          method: "POST",
          body: { settings: collect() },
        });
        hint.textContent = `候选 ${d.count} 人`;
      } catch { /* 网络抖动就先不更新 */ }
    }, 150);
  };
  // 每档难度的说明文案(候选数取自 META)
  const ps = (META && META.pool_sizes) || {};
  const fixed = `固定 8 次猜测${withTimer ? " · 整局限时 2 分钟" : ""}`;
  const DIFF_DESC = {
    easy: `谜底为 Major 常客或现役强队明星 · ${fixed}`,
    medium: `谜底为打过 2+ 次 Major 或现役职业哥 · ${fixed}`,
    hard: `全部合格谜底,包括冷门老哥 · ${fixed}`,
    top20: `谜底进过 HLTV 年度 Top20(2013–2025 全明星池,共 ${ps.top20 ?? "?"} 人),新手友好 · ${fixed}`,
    custom: "",          // 自定义档直接展开筛选行,不需要说明文案
  };
  const descEl = el.querySelector(".diff-desc");
  const applyDesc = (v) => {
    const txt = DIFF_DESC[v] || "";
    descEl.textContent = txt;
    el.querySelector(".diff-desc-row").classList.toggle("hidden", !txt);
  };
  applyDesc("medium");
  seg.querySelectorAll("button").forEach(b => b.onclick = () => {
    seg.querySelectorAll("button").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
    const custom = b.dataset.v === "custom";
    el.querySelector(".custom-rows").classList.toggle("hidden", !custom);
    applyDesc(b.dataset.v);
    if (onDifficulty) onDifficulty(b.dataset.v);
    updHint();
  });
  // 规则说明:点「?」在设置面板内展开/收起(内嵌块,不会被面板裁剪)
  const qtip = el.querySelector(".qtip");
  const rules = el.querySelector(".rules-pop");
  qtip.addEventListener("click", () => {
    qtip.classList.toggle("open");
    rules.classList.toggle("hidden");
    qtip.setAttribute("aria-expanded", String(!rules.classList.contains("hidden")));
  });
  el.querySelectorAll(".tag").forEach(t => t.onclick = () => {
    t.classList.toggle("on"); updHint();
  });
  el.querySelector(".active-only").addEventListener("change", updHint);
  el.querySelectorAll("select").forEach(s => s.addEventListener("change", updHint));
  updHint();
  return collect;
}
function range(a, b) { return Array.from({length: b - a + 1}, (_, i) => a + i); }

/* ---------------- autocomplete ---------------- */
function attachSuggest(inputEl, boxEl, onPick) {
  let items = [], sel = -1;
  const close = () => { boxEl.classList.add("hidden"); sel = -1; };
  inputEl.addEventListener("input", () => {
    const q = inputEl.value.trim().toLowerCase();
    if (q.length < 1) { close(); return; }
    const starts = [], contains = [];
    for (const p of PLAYERS) {
      const n = p.nickname.toLowerCase();
      if (n.startsWith(q)) starts.push(p);
      else if (n.includes(q) || (p.real_name || "").toLowerCase().includes(q)) contains.push(p);
    }
    const fame = (a, b) => (b.majors_count || 0) - (a.majors_count || 0);
    starts.sort(fame); contains.sort(fame);
    items = starts.concat(contains).slice(0, 9);
    if (!items.length) { close(); return; }
    boxEl.innerHTML = items.map((p, i) => `
      <div class="s-item" data-i="${i}">
        ${avaHtml(p)}
        <span class="s-copy">
          <span class="s-primary">${flagHtml(p.country, p.flag)} <b>${esc(p.nickname)}</b></span>
          <span class="s-real">${esc(p.real_name || "暂无真名资料")}</span>
        </span>
        <span class="s-team">${esc(p.team || "自由身")}</span>
      </div>`).join("");
    boxEl.classList.remove("hidden");
    boxEl.querySelectorAll(".s-item").forEach(d =>
      d.onclick = () => { close(); onPick(items[+d.dataset.i]); });
    sel = -1;
  });
  inputEl.addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) return;   // 输入法组合态的回车不当作提交
    const vis = !boxEl.classList.contains("hidden");
    if (e.key === "Enter") {
      e.preventDefault();
      // 先把选中项取出来再 close():close() 会把 sel 重置成 -1
      const picked = vis && sel >= 0 ? items[sel] : vis && items.length ? items[0] : null;
      if (picked) { close(); onPick(picked); }
      else if (inputEl.value.trim()) onPick({ nickname: inputEl.value.trim() });
    } else if (e.key === "ArrowDown" && vis) {
      e.preventDefault(); sel = Math.min(sel + 1, items.length - 1); mark();
    } else if (e.key === "ArrowUp" && vis) {
      e.preventDefault(); sel = Math.max(sel - 1, 0); mark();
    } else if (e.key === "Escape") close();
  });
  function mark() {
    boxEl.querySelectorAll(".s-item").forEach((d, i) =>
      d.classList.toggle("sel", i === sel));
  }
  document.addEventListener("click", (e) => {
    if (!boxEl.contains(e.target) && e.target !== inputEl) close();
  });
}
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c])); }

/* ---------------- grid rendering ---------------- */
const HEAD = ["选手", "国籍", "战队", "年龄", "位置", "MAJOR", "冠军"];
function c4Html() {
  // CS HUD 风格 C4:砖体+指示灯,urgent 时外圈爆闪光线亮起
  return `<svg class="c4" viewBox="0 0 24 26" aria-hidden="true">
    <g class="c4-rays" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
      <line x1="12" y1="3" x2="12" y2="0.8"/>
      <line x1="6.2" y1="5.2" x2="4.4" y2="3.4"/>
      <line x1="17.8" y1="5.2" x2="19.6" y2="3.4"/>
      <line x1="3.6" y1="10.4" x2="1.2" y2="9.8"/>
      <line x1="20.4" y1="10.4" x2="22.8" y2="9.8"/>
    </g>
    <rect x="4" y="8" width="16" height="15" rx="2" fill="currentColor" opacity=".18"/>
    <rect x="4" y="8" width="16" height="15" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/>
    <rect class="c4-led" x="7" y="11" width="10" height="4.5" rx="1" fill="currentColor"/>
    <line x1="7" y1="19" x2="17" y2="19" stroke="currentColor" stroke-width="1.2" opacity=".5"/>
    <line x1="7" y1="21" x2="13" y2="21" stroke="currentColor" stroke-width="1.2" opacity=".35"/>
  </svg>`;
}
function flagHtml(country, flagPath) {
  if (flagPath) return `<img class="fl" src="${flagPath}" alt="${esc(country)}" title="${esc(country)}">`;
  const f = flag(country);
  return f ? `<span class="fl-txt">${f}</span>` : "";
}
function avaHtml(p) {
  if (p.photo) return `<img class="ava" src="${p.photo}" alt="${esc(p.nickname || "选手")}头像" loading="lazy">`;
  const init = esc((p.nickname || "?").slice(0, 2).toUpperCase());
  return `<div class="ava fallback">${init}</div>`;
}
function rowHtml(row) {
  const p = row.player, byKey = {};
  row.cells.forEach(x => byKey[x.key] = x);
  const arrow = (x) => x.dir === "up" ? ' <span class="arrow">▲</span>' :
                       x.dir === "down" ? ' <span class="arrow">▼</span>' : "";
  const n = byKey.nationality, t = byKey.team, a = byKey.age,
        r = byKey.role, m = byKey.majors, w = byKey.majors_won;
  const tlogo = p.team_logo && p.team
    ? `<img class="tlogo${p.team_logo.includes("_lm.") ? " chip" : ""}" src="${p.team_logo}" alt="" loading="lazy">` : "";
  guessedPlayerProfiles.set(p.page, {
    ...p,
    country: n.value,
    region: n.extra,
    team_label: t.value,
    age: a.value,
    role: r.value,
    majors_count: m.value,
    majors_won: w ? w.value : 0,
  });
  return `<div class="grow">
    <div class="cell name">
      <button class="player-trigger" type="button" data-player-page="${esc(p.page)}"
        aria-haspopup="dialog" aria-label="查看 ${esc(p.nickname)} 的资料">
        ${avaHtml(p)}
        <span><span class="nick">${esc(p.nickname)}</span>
        <span class="small">${esc(p.real_name || "")}</span></span>
      </button>
    </div>
    <div class="cell ${n.state}" title="${esc(n.value)}"><span class="row1">${flagHtml(n.value, p.flag)} ${esc(cnCountry(n.value))}</span>
      <span class="small">${REGION_CN[n.extra] || ""}</span></div>
    <div class="cell ${t.state}"><span class="row1">${tlogo}<span>${esc(t.value)}</span></span></div>
    <div class="cell ${a.state}"><span class="num">${a.value}${arrow(a)}</span></div>
    <div class="cell ${r.state}">${esc(cnRole(r.value))}</div>
    <div class="cell ${m.state}"><span class="num">${m.value}${arrow(m)}</span></div>
    ${w ? `<div class="cell ${w.state}"><span class="num">${w.value}${arrow(w)}</span></div>` : '<div class="cell gray">-</div>'}
  </div>`;
}

function openPlayerProfile(page) {
  const p = guessedPlayerProfiles.get(page);
  if (!p) return;
  const photo = p.photo
    ? `<img class="profile-photo" src="${p.photo}" alt="${esc(p.nickname)} 头像">`
    : `<div class="profile-photo fallback">${esc(p.nickname.slice(0, 2).toUpperCase())}</div>`;
  const tlogo = p.team_logo && p.team_label !== "自由身"
    ? `<img class="tlogo${p.team_logo.includes("_lm.") ? " chip" : ""}" src="${p.team_logo}" alt="">`
    : "";
  const liq = `https://liquipedia.net/counterstrike/${encodeURIComponent(
    (p.page || p.nickname).replace(/ /g, "_"))}`;
  const hltv = `https://www.hltv.org/search?query=${encodeURIComponent(p.nickname)}`;
  $("player-profile-content").innerHTML = `
    <div class="player-profile">
      <div class="profile-identity">
        ${photo}
        <div>
          <div class="profile-name">${flagHtml(p.country, p.flag)} ${esc(p.nickname)}</div>
          <div class="profile-real">${esc(p.real_name || "暂无真名资料")}</div>
          <span class="profile-role">${esc(cnRole(p.role))}</span>
        </div>
      </div>
      <div class="profile-facts">
        <div><span>国籍 / 赛区</span><b>${esc(cnCountry(p.country))} · ${esc(REGION_CN[p.region] || p.region)}</b></div>
        <div><span>当前战队</span><b>${tlogo}${esc(p.team_label || p.team || "自由身")}</b></div>
        <div><span>年龄</span><b>${p.age ?? "?"} 岁</b></div>
        <div><span>参加 Major</span><b>${p.majors_count ?? 0} 次</b></div>
        <div><span>Major 冠军</span><b>${p.majors_won ?? 0} 次</b></div>
      </div>
      <div class="profile-links">
        <a href="${liq}" target="_blank" rel="noopener">Liquipedia</a>
        <a href="${hltv}" target="_blank" rel="noopener">HLTV</a>
      </div>
    </div>`;
  profileReturnFocus = document.activeElement;
  $("player-modal").classList.remove("hidden");
  $("player-profile-close").focus();
}

function closePlayerProfile() {
  $("player-modal").classList.add("hidden");
  if (profileReturnFocus && document.contains(profileReturnFocus)) profileReturnFocus.focus();
  profileReturnFocus = null;
}
function renderGrid(el, rows) {
  el.innerHTML = `<div class="grow header">${HEAD.map(h => `<div>${h}</div>`).join("")}</div>`
    + rows.map(rowHtml).join("");
}
function syncGrid(el, rows) {
  // 只增量追加新行:整格重绘会让头像重载、翻转动画重播,
  // 对手每次行动广播状态时画面就"闪一下"
  el.querySelectorAll(".grow.ghost").forEach(n => n.remove());
  const rendered = el.childElementCount ? el.childElementCount - 1 : 0;
  if (!el.childElementCount || rendered > rows.length) { renderGrid(el, rows); return; }
  for (let i = rendered; i < rows.length; i++)
    el.insertAdjacentHTML("beforeend", rowHtml(rows[i]));
}
function pipsHtml(used, total) {
  let h = '<span class="pips">';
  for (let i = 0; i < total; i++)
    h += `<span class="pip${i < used ? " used" : ""}"></span>`;
  return h + "</span>";
}
function syncGhosts(el, used, total) {
  // 新版 UI:剩余猜测画成幽灵空行,棋盘"看得见还剩几发子弹"
  el.querySelectorAll(".grow.ghost").forEach(n => n.remove());
  if (!uiV2() || !total) return;
  let h = "";
  for (let i = used; i < total; i++)
    h += `<div class="grow ghost"><div class="cell name"><span class="g-idx">${
      String(i + 1).padStart(2, "0")}</span></div>${'<div class="cell"></div>'.repeat(6)}</div>`;
  if (h) el.insertAdjacentHTML("beforeend", h);
}
function killfeed(target) {
  // 新版 UI:猜中瞬间的 killfeed 横幅,结算弹窗出来前先给情绪
  if (!uiV2() || !target) return;
  const el = document.createElement("div");
  el.className = "killfeed";
  el.innerHTML = `<b>你</b><svg viewBox="0 0 24 24" aria-hidden="true">`
    + `<path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z"/></svg><b>${esc(target)}</b>`;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3400);
}
let lastAnswer = null;   // 最近渲染的谜底,供纠错反馈定位选手
function answerCard(a) {
  lastAnswer = a;
  const photo = a.photo ? `<img class="photo" src="${a.photo}" alt="">`
    : `<div class="photo fallback">${esc(a.nickname.slice(0, 2).toUpperCase())}</div>`;
  const tlogo = a.team_logo ? `<img class="tlogo${a.team_logo.includes("_lm.") ? " chip" : ""}" src="${a.team_logo}" alt="">` : "";
  const liq = `https://liquipedia.net/counterstrike/${encodeURIComponent((a.page || a.nickname).replace(/ /g, "_"))}`;
  const hltv = a.hltv_url || `https://www.hltv.org/search?query=${encodeURIComponent(a.nickname)}`;
  return `<div class="answer-card">${photo}
    <div>
      <div class="a-name">${flagHtml(a.country, a.flag)} ${esc(a.nickname)}</div>
      <div class="a-real">${esc(a.real_name || "")}</div>
      <div class="a-facts">
        <span>${esc(cnCountry(a.country))} · ${REGION_CN[a.region] || a.region}</span>
        <span><b>${a.age ?? "?"}</b> 岁</span>
        <span>${tlogo}${esc(a.team_label || a.team || "自由身")}</span>
        <span>${esc(cnRole(a.role))}</span>
        <span><b>${a.majors_count}</b> 次 Major</span>
        <span><b>${a.majors_won ?? 0}</b> 冠</span>
      </div>
      <div class="a-links">
        <a href="${liq}" target="_blank" rel="noopener">Liquipedia</a>
        <a href="${hltv}" target="_blank" rel="noopener">HLTV</a>
        <button class="linklike" onclick="openFeedback()">信息有误?</button>
      </div>
    </div>
  </div>`;
}

/* ---------------- 玩家纠错反馈 ---------------- */
function feedbackContext() {
  if (room.code && !$("view-room").classList.contains("hidden"))
    return `room ${room.code}`;
  if (soloGame) return soloGame.mode;
  return "";
}
function openFeedback() {
  $("fb-player").textContent = lastAnswer
    ? `${lastAnswer.nickname}(${lastAnswer.real_name || "?"})` : "整体反馈";
  $("fb-text").value = "";
  $("fb-modal").classList.remove("hidden");
  $("fb-text").focus();
}
async function sendFeedback() {
  const message = $("fb-text").value.trim();
  if (!message) { toast("先写点内容再提交"); return; }
  try {
    await api("/api/feedback", { method: "POST", body: {
      page: lastAnswer ? lastAnswer.page || "" : "",
      message, context: feedbackContext(),
    }});
    $("fb-modal").classList.add("hidden");
    toast("收到,感谢纠错!核实后会更新数据");
  } catch (e) { toast(e.message); }
}

/* ---------------- 胜负结算弹窗 ---------------- */
function showEndOverlay(kind, title, sub, answer, buttons) {
  $("end-verdict").textContent = title;
  $("end-verdict").className = "end-verdict " + kind;
  $("end-sub").textContent = sub || "";
  $("end-card").innerHTML = answer ? answerCard(answer) : "";
  $("end-btns").innerHTML = buttons || "";
  const ov = $("end-overlay");
  ov.classList.add("hidden");
  void ov.offsetWidth;               // 重启动画
  ov.classList.remove("hidden");
}
function closeEndOverlay() { $("end-overlay").classList.add("hidden"); }
function overlayAgain() { closeEndOverlay(); startUnlimited(); }
function overlayTranscript() { closeEndOverlay(); showTranscript(); }

/* ---------------- solo ---------------- */
let getUnlimitedSettings = null;
function showUnlimitedSetup() {
  go("unlimited-setup");
  if (!getUnlimitedSettings) getUnlimitedSettings = renderSettings("settings-unlimited");
}
async function startDaily() {
  const saved = JSON.parse(localStorage.getItem("cstrikle_daily") || "null");
  const today = new Date().toISOString().slice(0, 10);
  if (saved && saved.date === today) {
    try { soloGame = await api(`/api/game/${saved.id}`); openGame(); return; }
    catch {}
  }
  try {
    soloGame = await api("/api/game", { method: "POST", body: { mode: "daily" } });
    localStorage.setItem("cstrikle_daily", JSON.stringify({ date: today, id: soloGame.id }));
    openGame();
  } catch (e) { toast(e.message); }
}
async function startUnlimited() {
  const settings = getUnlimitedSettings ? getUnlimitedSettings() : null;
  try {
    soloGame = await api("/api/game", { method: "POST", body: { mode: "unlimited", settings } });
    openGame();
  } catch (e) { toast(e.message); }
}
function openGame() {
  go("game");
  $("guess-input").value = "";
  renderSolo();
  $("guess-input").focus();
}
function renderSolo() {
  const g = soloGame;
  $("game-mode-label").innerHTML = g.mode === "daily"
    ? `每日挑战 <b>${new Date().toISOString().slice(0, 10)}</b>` : "无限模式";
  $("game-remaining").innerHTML = pipsHtml(g.guesses.length, g.settings.max_guesses);
  $("game-pool").textContent = `候选 ${g.pool_size} 人`;
  renderGrid($("grid"), g.guesses);
  syncGhosts($("grid"), g.guesses.length,
    g.status === "playing" ? g.settings.max_guesses : 0);
  const res = $("game-result");
  const again = $("btn-again");
  if (g.status === "playing") {
    res.classList.add("hidden"); again.classList.add("hidden");
    $("guess-input").disabled = false;
  } else {
    res.classList.remove("hidden");
    res.className = "result " + (g.status === "won" ? "win" : "lose");
    res.innerHTML = `<div class="verdict">${g.status === "won"
        ? `ACE — ${g.guesses.length} 次猜中` : "TIME OUT — 次数用完了"}</div>`
      + answerCard(g.answer)
      + (g.mode === "daily" ? `<div class="r-extra"><button onclick="shareDaily()">复制战绩</button></div>` : "");
    again.classList.toggle("hidden", g.mode === "daily");
    $("guess-input").disabled = true;
  }
}
async function soloGuess(p) {
  if (!soloGame || soloGame.status !== "playing") return;
  try {
    soloGame = await api(`/api/game/${soloGame.id}/guess`, { method: "POST", body: { name: p.page || p.nickname } });
    $("guess-input").value = "";
    renderSolo();
    if (soloGame.status !== "playing") {
      const g = soloGame;
      if (g.status === "won") killfeed(g.answer && g.answer.nickname);
      const btns = (g.mode === "daily"
        ? `<button class="primary" onclick="shareDaily()">复制战绩</button>`
        : `<button class="primary" onclick="overlayAgain()">再来一局</button>`)
        + `<button onclick="closeEndOverlay()">关闭</button>`;
      setTimeout(() => showEndOverlay(
        g.status === "won" ? "win" : "lose",
        g.status === "won" ? "ACE!" : "TIME OUT",
        g.status === "won" ? `${g.guesses.length} 次猜中` : "次数用完了,谜底是他",
        g.answer, btns), 900);   // 等最后一行翻完再弹
    }
  } catch (e) { toast(e.message); }
}
function shareDaily() {
  // Wordle 式彩色矩阵:颜色本身就是战报,末尾带上入口链接
  const g = soloGame;
  const map = { green: "🟩", yellow: "🟨", gray: "⬛" };
  const date = new Date().toISOString().slice(0, 10);
  const score = g.status === "won" ? g.guesses.length : "X";
  const txt = [
    `FribergCS2 每日挑战 ${date} ${score}/${g.settings.max_guesses}`,
    ...g.guesses.map(r => r.cells.map(c => map[c.state]).join("")),
    location.origin,
  ].join("\n");
  copyText(txt).then(ok =>
    toast(ok ? "战绩已复制,去嘲讽朋友吧" : "复制失败,浏览器没给剪贴板权限"));
}
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {}
  try {           // http 部署或旧浏览器:退回隐藏 textarea + execCommand
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch { return false; }
}

/* ---------------- versus ---------------- */
let getRoomSettings = null;
function lobbyName(fallback) {
  const name = $("lobby-name").value.trim();
  if (name) localStorage.setItem("cstrikle_name", name);
  return name || fallback;
}
async function createRoom() {
  const vsAi = $("vs-ai").checked;
  const settings = getRoomSettings();
  try {
    const r = await api("/api/room", { method: "POST", body: {
      name: lobbyName("玩家1"),
      settings, vs_ai: vsAi, ai_level: $("ai-level").value,
    }});
    enterRoom(r.code, r.token, vsAi);
    if (!vsAi) toast(`房间码 ${r.code},发给朋友让他加入`, 6000);
  } catch (e) { toast(e.message); }
}
async function joinRoom() {
  const code = $("join-code").value.trim().toUpperCase();
  if (code.length < 4) { toast("输入 4 位房间码"); return; }
  try {
    const r = await api(`/api/room/${code}/join`, { method: "POST", body: {
      name: lobbyName("玩家2"),
    }});
    enterRoom(r.code, r.token, false);
  } catch (e) { toast(e.message); }
}
/* ---------------- 随机匹配 ---------------- */
let match = { ticket: null, timer: null };
function matchUi(on) {
  $("btn-match").classList.toggle("hidden", on);
  $("mm-status").classList.toggle("hidden", !on);
}
async function startMatch() {
  const name = lobbyName("路人玩家");
  const difficulty = document.querySelector(".mm-seg .on").dataset.v;
  try {
    const r = await api("/api/match/join", { method: "POST", body: { name, difficulty } });
    if (r.matched) { enterRoom(r.code, r.token, false); toast("匹配成功,开打!"); return; }
    match.ticket = r.ticket;
    matchUi(true);
    match.timer = setInterval(pollMatch, 2000);
  } catch (e) { toast(e.message); }
}
async function pollMatch() {
  if (!match.ticket) return;
  try {
    const r = await api(`/api/match/poll/${match.ticket}`);
    if (r.matched) {
      stopMatch();
      enterRoom(r.code, r.token, false);
      toast("匹配成功,开打!");
    }
  } catch {
    stopMatch();
    toast("匹配已过期,请重新开始");
  }
}
function stopMatch() {
  clearInterval(match.timer);
  match = { ticket: null, timer: null };
  matchUi(false);
}
function cancelMatch() {
  if (match.ticket) api(`/api/match/${match.ticket}`, { method: "DELETE" }).catch(() => {});
  stopMatch();
}

function enterRoom(code, token, vsAi) {
  room = {
    ws: null, code, token, state: null, vsAi,
    chat: [], lastStatus: null,
  };
  streamerReveal = false;
  go("room");
  $("room-code").textContent = code;
  $("room-guess-input").value = "";
  $("chat-log").innerHTML = "";
  $("room-grid").innerHTML = "";      // 清掉上一局残留,增量渲染按空网格起步
  $("btn-transcript").classList.add("hidden");
  $("btn-rematch").classList.add("hidden");
  $("room-result").classList.add("hidden");
  $("room-result").dataset.spoiler = "";
  $("opp-reveal-main").innerHTML = "";
  updateStreamerUi();
  connectWs();
}
function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/room/${room.code}?token=${room.token}`);
  room.ws = ws;
  ws.onmessage = (ev) => handleWs(JSON.parse(ev.data));
  ws.onclose = () => {
    if (room.state && room.state.status !== "over" && $("view-room") &&
        !$("view-room").classList.contains("hidden")) {
      setTimeout(() => { if (room.ws === ws) connectWs(); }, 1500);
    }
  };
}
function handleWs(msg) {
  if (msg.type === "state") {
    room.state = msg;
    mergeChat(msg.chat || []);
    renderRoom();
  }
  else if (msg.type === "chat") mergeChat([msg]);
  else if (msg.type === "error") toast(msg.message);
  else if (msg.type === "ai_status") {
    const el = $("ai-status");
    if (msg.state === "idle") el.classList.add("hidden");
    else {
      el.classList.remove("hidden");
      el.textContent = msg.detail || (
        msg.state === "searching" ? "AI 正在上网搜资料…" : "AI 正在分析局面…"
      );
    }
  }
}
let turnTimerInt = null;
function streamerPrivacyActive() {
  return streamerMode && !streamerReveal;
}
function visibleOpponentName(name, fallback = "对手") {
  return streamerPrivacyActive() ? fallback : (name || fallback);
}
function visibleWinnerName(name, you) {
  if (!streamerPrivacyActive() || name === "draw" || name === you.name) return name;
  return "对手";
}
function sanitizeSystemChat(text) {
  let shown = String(text || "");
  if (!streamerPrivacyActive() || !room.state || !room.state.opponent) return shown;
  const opponentName = room.state.opponent.name;
  if (opponentName) shown = shown.split(opponentName).join("对手");
  return shown;
}
function chatKey(m) {
  return `${m.ts || ""}\u241f${m.from || ""}\u241f${m.text || ""}`;
}
function mergeChat(messages) {
  if (!Array.isArray(room.chat)) room.chat = [];
  const known = new Set(room.chat.map(chatKey));
  for (const message of messages) {
    const key = chatKey(message);
    if (!known.has(key)) {
      room.chat.push(message);
      known.add(key);
    }
  }
  room.chat = room.chat.slice(-100);
  renderChat();
}
function updateStreamerUi() {
  const toggle = $("streamer-mode");
  if (toggle) toggle.checked = streamerMode;
  const reveal = $("chat-reveal");
  const note = $("chat-privacy-note");
  if (!reveal || !note) return;
  reveal.classList.toggle("hidden", !streamerMode);
  reveal.classList.toggle("revealed", streamerReveal);
  reveal.setAttribute("aria-pressed", String(streamerReveal));
  reveal.setAttribute("aria-label", streamerReveal
    ? "重新隐藏对手和聊天内容" : "临时显示对手和聊天内容");
  reveal.title = reveal.getAttribute("aria-label");
  note.classList.toggle("hidden", !streamerMode);
  note.textContent = streamerReveal ? "主播模式 · 临时显示中" : "主播模式已隐藏";
}
function toggleStreamerReveal() {
  if (!streamerMode) return;
  streamerReveal = !streamerReveal;
  updateStreamerUi();
  if (room.state) renderRoom();
  else renderChat();
}
function renderRoom() {
  const s = room.state;
  const you = s.you, opp = s.opponent;
  const previousStatus = room.lastStatus;
  const justEnded = s.status === "over" && previousStatus === "playing";
  const justRematched = s.status === "playing" && previousStatus === "over";
  room.lastStatus = s.status;
  if (justRematched) closeEndOverlay();

  // 整局限时倒计时
  clearInterval(turnTimerInt);
  const tt = $("turn-timer");
  if (s.status === "playing" && s.deadline) {
    const offset = (s.now || Date.now() / 1000) - Date.now() / 1000;
    const upd = () => {
      const left = Math.max(0, Math.round(s.deadline - offset - Date.now() / 1000));
      tt.innerHTML = `${c4Html()} ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
      tt.classList.toggle("urgent", left <= 30);
    };
    upd();
    turnTimerInt = setInterval(upd, 500);
    tt.classList.remove("hidden");
  } else tt.classList.add("hidden");
  $("room-status").textContent = s.status === "waiting" ? "等待对手加入…"
    : s.status === "playing" ? "对局进行中"
    : opp && opp.rematch_ready ? "对手已准备再来一局" : "对局结束";
  $("room-remaining").innerHTML = pipsHtml(you.rows.length, s.settings.max_guesses);
  syncGrid($("room-grid"), you.rows);
  syncGhosts($("room-grid"), you.rows.length,
    s.status === "playing" ? s.settings.max_guesses : 0);
  $("room-guess-input").disabled = s.status !== "playing" || you.status !== "playing";

  // opponent panel
  if (opp) {
    $("opp-name").textContent = visibleOpponentName(opp.name, "对手（已隐藏）")
      + (opp.present === false ? "(已离开)" : "");
    $("opp-remaining").textContent = `对手剩余次数 ${opp.remaining}`;
    const MINI = { nationality: "国", team: "队", age: "龄", role: "位",
                   majors: "M", majors_won: "冠" };
    $("opp-grid").innerHTML = opp.colors.map((r, i) => {
      const hit = r.every(c => c.state === "green");
      return `<div class="mini-row${hit ? " hit" : ""}"><span class="mini-idx">${i + 1}</span>${r.map(c =>
        `<div class="mini-cell ${c.state}">${MINI[c.key] || ""}${c.dir === "up" ? "▲" : c.dir === "down" ? "▼" : ""}</div>`
      ).join("")}${hit ? '<span class="mini-hit">命中</span>' : ""}</div>`;
    }).join("");
  } else {
    $("opp-name").textContent = "等待对手…";
    $("opp-grid").innerHTML = ""; $("opp-remaining").textContent = "";
  }

  renderChat();

  const res = $("room-result");
  if (s.status === "over") {
    res.dataset.spoiler = "";
    res.classList.remove("hidden");
    const iWon = s.winner === you.name;
    const shownWinner = visibleWinnerName(s.winner, you);
    res.className = "result " + (iWon ? "win" : s.winner === "draw" ? "" : "lose");
    res.innerHTML = `<div class="verdict">${s.winner === "draw"
        ? "DRAW — 平局,谁都没猜出来"
        : iWon ? "VICTORY — 你先猜中了" : `DEFEAT — ${esc(shownWinner)} 先猜中了`}</div>`
      + answerCard(s.answer);
    if (opp && opp.is_ai) $("btn-transcript").classList.remove("hidden");
    // 对手已经跑了就没有「再来一局」可言
    const rematchGone = !!(opp && !opp.is_ai && opp.present === false);
    const rematchReady = !!you.rematch_ready;
    const rematchBtn = $("btn-rematch");
    rematchBtn.classList.toggle("hidden", rematchGone);
    rematchBtn.disabled = rematchReady;
    rematchBtn.textContent = rematchReady ? "已准备，等待对手" : "再来一局";
    const overlayRematch = $("btn-rematch-overlay");
    if (overlayRematch) {
      overlayRematch.disabled = rematchReady;
      overlayRematch.textContent = rematchReady
        ? "已准备，等待对手" : "再来一局";
    }
    const rev = $("opp-reveal-main");
    if (s.opponent_rows && s.opponent_rows.length) {
      rev.innerHTML = `<h3 class="reveal-title">${esc(
        visibleOpponentName(opp ? opp.name : "", "对手")
      )} 的猜测</h3>`;
      const div = document.createElement("div");
      div.className = "grid";
      renderGrid(div, s.opponent_rows);
      rev.appendChild(div);
    } else rev.innerHTML = "";
    $("ai-status").classList.add("hidden");
    if (justEnded) {
      const iWon = s.winner === you.name;
      if (iWon && s.answer) killfeed(s.answer.nickname);
      const kind = iWon ? "win" : s.winner === "draw" ? "draw" : "lose";
      const title = iWon ? "VICTORY" : s.winner === "draw" ? "DRAW" : "DEFEAT";
      const sub = iWon ? "你先猜中了" : s.winner === "draw" ? "谁都没猜出来"
        : `${shownWinner} 先猜中了`;
      const oppGone = opp && !opp.is_ai && opp.present === false;
      const btns = (oppGone ? ""
        : `<button id="btn-rematch-overlay" class="primary" onclick="roomRematch()"
             ${rematchReady ? "disabled" : ""}>${rematchReady
               ? "已准备，等待对手" : "再来一局"}</button>`)
        + (opp && opp.is_ai
        ? `<button onclick="overlayTranscript()">查看 AI 决策回放</button>` : "")
        + `<button onclick="closeEndOverlay()">关闭</button>`;
      setTimeout(() => {
        showEndOverlay(kind, title, sub, s.answer, btns);
        // 结算动画延迟期间可能已经点过页面内按钮，避免弹出旧的可点击状态。
        const liveRematch = $("btn-rematch-overlay");
        const liveReady = !!(room.state && room.state.you.rematch_ready);
        if (liveRematch && liveReady) {
          liveRematch.disabled = true;
          liveRematch.textContent = "已准备，等待对手";
        }
      }, 700);
    }
    if (!$("end-overlay").classList.contains("hidden")) {
      $("end-sub").textContent = iWon ? "你先猜中了"
        : s.winner === "draw" ? "谁都没猜出来"
        : `${shownWinner} 先猜中了`;
    }
  } else {
    if (s.answer_spoiler) {
      // 你已出局:可折叠偷看谜底,避免重复渲染打断已展开的状态
      if (res.dataset.spoiler !== "1") {
        res.dataset.spoiler = "1";
        res.classList.remove("hidden");
        res.className = "result";
        res.innerHTML = `<div class="verdict">你已出局 — 对手还在打</div>
          <div class="r-extra" style="padding-top:12px">
            <details><summary>偷看谜底(剧透警告)</summary>${answerCard(s.answer_spoiler)}</details>
          </div>`;
      }
    } else { res.classList.add("hidden"); res.dataset.spoiler = ""; }
    $("opp-reveal-main").innerHTML = "";
    $("btn-transcript").classList.add("hidden");
    $("btn-rematch").classList.add("hidden");
  }
}
function renderChat() {
  const log = $("chat-log");
  if (!log) return;
  log.innerHTML = "";
  for (const m of (room.chat || [])) {
    const div = document.createElement("div");
    const isSystem = m.from === "系统";
    const isAi = m.from && m.from.startsWith("AI");
    div.className = isSystem ? "c-sys" : isAi ? "c-ai" : "";
    if (isSystem) {
      div.textContent = sanitizeSystemChat(m.text);
    } else if (streamerPrivacyActive()) {
      const isYou = room.state && m.from === room.state.you.name;
      div.innerHTML = `<span class="c-from">${isYou ? "你" : "对手"}:</span> `
        + `<span class="c-masked">••••••••</span>`;
    } else {
      div.innerHTML = `<span class="c-from">${esc(m.from)}:</span> ${esc(m.text)}`;
    }
    log.appendChild(div);
  }
  log.scrollTop = log.scrollHeight;
}
function wsReady() {
  if (!room.ws || room.ws.readyState !== WebSocket.OPEN) {
    toast("连接中,稍等一下…");
    return false;
  }
  return true;
}
function sendChat() {
  const t = $("chat-text").value.trim();
  if (!t || !wsReady()) return;
  room.ws.send(JSON.stringify({ type: "chat", text: t }));
  $("chat-text").value = "";
}
function roomGuess(p) {
  if (!wsReady()) return;
  room.ws.send(JSON.stringify({ type: "guess", name: p.page || p.nickname }));
  $("room-guess-input").value = "";
}
function leaveRoom() {
  clearInterval(turnTimerInt);
  go("versus-lobby");        // go() 里会发 leave 并断开
}
async function roomRematch() {
  try {
    const r = await api(`/api/room/${room.code}/rematch`, {
      method: "POST", headers: { "X-Room-Token": room.token },
    });
    if (r.started) closeEndOverlay();
    else toast("已准备，等待对手确认");
    if (!room.ws || room.ws.readyState !== WebSocket.OPEN) connectWs();
  } catch (e) {
    toast(e.message);
    if (e.status === 409) {         // 对手已离开,回对战大厅
      closeEndOverlay();
      leaveRoom();
    }
  }
}
async function showTranscript() {
  try {
    const t = await api(`/api/room/${room.code}/transcript`, {
      headers: { "X-Room-Token": room.token },
    });
    const levelName = {easy: "下饭", normal: "普通", hard: "作弊"}[t.level] || "";
    $("transcript-model").textContent = levelName ? `· ${levelName}` : "";
    $("transcript-body").innerHTML = t.transcript.map(turn => `
      <div class="turn-block">
        <h4>第 ${turn.turn} 次猜测</h4>
        ${turn.events.map(evHtml).join("")}
      </div>`).join("") || "<p class='dim'>AI 还没行动过。</p>";
    $("modal").classList.remove("hidden");
  } catch (e) { toast(e.message); }
}
function evHtml(e) {
  switch (e.type) {
    case "decision": {
      const explanation = (e.explanation || []).map(line =>
        `<li>${esc(line)}</li>`
      ).join("");
      const shortlist = (e.shortlist || []).join("、");
      return `<div class="ev ev-solver">
        <div class="decision-head">
          <span>${esc(e.strategy)}难度</span>
          <b>${esc(e.chosen)}</b>
        </div>
        <div class="decision-summary">${esc(e.summary)}</div>
        ${explanation ? `<ul class="decision-steps">${explanation}</ul>` : ""}
        ${shortlist ? `<details><summary>这轮考虑过的人</summary><p>${esc(shortlist)}</p></details>` : ""}
      </div>`;
    }
    case "solver": {
      const explanation = (e.explanation || []).map(line =>
        `<li>${esc(line)}</li>`
      ).join("");
      return `<div class="ev ev-solver">
        <div class="decision-head">
          <span>作弊难度</span>
          <b>${esc(e.recommended)}</b>
        </div>
        <div class="decision-summary">根据当前线索，还剩 ${e.candidate_count} 名可能人选。</div>
        ${explanation ? `<ul class="decision-steps">${explanation}</ul>` : ""}
      </div>`;
    }
    case "reasoning": return `<div class="ev"><details><summary>AI 自己的想法</summary><pre>${esc(e.text)}</pre></details></div>`;
    case "thinking": return `<div class="ev ev-thinking"><b>AI 的选择理由</b><br>${esc(e.text)}</div>`;
    case "search": return `<div class="ev ev-search">搜索:「${esc(e.query)}」</div>`;
    case "search_result": return `<div class="ev"><details><summary>搜索结果</summary><pre>${esc(e.text)}</pre></details></div>`;
    case "say": return `<div class="ev ev-say">AI 聊天:${esc(e.text)}</div>`;
    case "guess": return `<div class="ev ev-guess">提交猜测:${esc(e.name)}</div>`;
    case "guess_rejected": return `<div class="ev ev-rejected">想猜 ${esc(e.name)} 被驳回:${esc(e.reason)}</div>`;
    case "forced_guess": return `<div class="ev ev-rejected">${esc(e.reason)}:${esc(e.name)}</div>`;
    default: return "";
  }
}

/* ---------------- localhost UI preview ---------------- */
function mockRow(nickname, states, facts = {}) {
  const p = PLAYERS.find(x => x.nickname.toLowerCase() === nickname.toLowerCase())
    || PLAYERS[0];
  if (!p) return null;
  const values = {
    nationality: [p.country, p.region],
    team: [p.team_label || p.team || "自由身", null],
    age: [facts.age ?? p.age ?? "?", null],
    role: [facts.role || p.role || "Rifler", null],
    majors: [p.majors_count, null],
    majors_won: [p.majors_won, null],
  };
  return {
    player: p,
    correct: false,
    cells: Object.entries(values).map(([key, [value, extra]], i) => ({
      key, value, extra,
      state: states[i] || "gray",
      dir: key === "age" || key === "majors" ? (i % 2 ? "down" : "up") : null,
    })),
  };
}
function openLocalMockPreview() {
  const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);
  if (!localHosts.has(location.hostname)
      || new URLSearchParams(location.search).get("mock") !== "streamer") return;
  const rows = [
    mockRow(
      "ZywOo",
      ["yellow", "gray", "yellow", "green", "gray", "gray"],
      {age: 25, role: "AWPer"},
    ),
    mockRow(
      "s1mple",
      ["green", "green", "gray", "yellow", "yellow", "gray"],
      {age: 28, role: "AWPer"},
    ),
  ].filter(Boolean);
  room = {
    ws: null, code: "MOCK", token: null, vsAi: false,
    chat: [
      {ts: 1, from: "系统", text: "VeryRecognizableFriend 加入了房间"},
      {ts: 2, from: "VeryRecognizableFriend", text: "这把我已经锁定答案了"},
      {ts: 3, from: "主播本人", text: "那就看看谁更快"},
    ],
    lastStatus: "playing",
    state: {
      type: "state", status: "playing",
      now: Date.now() / 1000, deadline: Date.now() / 1000 + 92,
      settings: {max_guesses: 8},
      you: {
        name: "主播本人", rows, status: "playing",
        rematch_ready: false,
      },
      opponent: {
        name: "VeryRecognizableFriend", present: true, remaining: 5,
        is_ai: false, rematch_ready: false,
        colors: [
          ["gray", "yellow", "gray", "green", "gray", "gray"],
          ["yellow", "green", "yellow", "gray", "yellow", "gray"],
          ["green", "green", "gray", "yellow", "yellow", "gray"],
        ].map(row => row.map((state, i) => ({
          key: ["nationality", "team", "age", "role", "majors", "majors_won"][i],
          state, dir: i === 2 ? "up" : null,
        }))),
      },
    },
  };
  streamerMode = true;
  streamerReveal = false;
  $("room-code").textContent = "MOCK";
  $("room-grid").innerHTML = "";
  $("room-result").classList.add("hidden");
  $("opp-reveal-main").innerHTML = "";
  go("room");
  updateStreamerUi();
  renderRoom();
}

/* ---------------- init ---------------- */
async function init() {
  try {
    [META, PLAYERS] = await Promise.all([api("/api/meta"), api("/api/players")]);
    $("meta-info").innerHTML =
      `<span>选手库 ${META.player_count} 人</span>`
      + `<span>更新于 ${META.db_generated_at.slice(0, 10)}</span>`;
    if (!META.ai_enabled) $("vs-ai").disabled = true;
  } catch (e) { toast("加载选手库失败: " + e.message); }
  getRoomSettings = renderSettings("settings-room", {
    withGuesses: true, withTimer: true,
    // 自定义难度不设上限,禁止配 AI(防止无限烧模型)
    onDifficulty: (d) => {
      const custom = d === "custom";
      const ai = $("vs-ai");
      if (custom) ai.checked = false;
      ai.disabled = custom || !(META && META.ai_enabled);
      $("vs-ai-note").classList.toggle("hidden", !custom);
      $("ai-level-row").classList.toggle("hidden", !ai.checked);
    },
  });
  attachSuggest($("guess-input"), $("suggest"), soloGuess);
  attachSuggest($("room-guess-input"), $("room-suggest"), roomGuess);
  document.addEventListener("click", e => {
    const trigger = e.target.closest(".player-trigger");
    if (trigger) openPlayerProfile(trigger.dataset.playerPage);
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !$("player-modal").classList.contains("hidden"))
      closePlayerProfile();
  });
  $("vs-ai").addEventListener("change", () => {
    $("ai-level-row").classList.toggle("hidden", !$("vs-ai").checked);
  });
  $("chat-text").addEventListener("keydown", e => { if (e.key === "Enter") sendChat(); });
  const saved = localStorage.getItem("cstrikle_name") || "";
  $("lobby-name").value = saved;
  $("streamer-mode").checked = streamerMode;
  $("streamer-mode").addEventListener("change", e => {
    streamerMode = e.target.checked;
    streamerReveal = false;
    localStorage.setItem(STREAMER_MODE_KEY, streamerMode ? "1" : "0");
    updateStreamerUi();
    if (room.state) renderRoom();
    else renderChat();
  });
  updateStreamerUi();
  updateUiToggle();
  document.querySelectorAll(".mm-seg button").forEach(b => b.onclick = () => {
    document.querySelectorAll(".mm-seg button").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
  });
  openLocalMockPreview();
}
init();
