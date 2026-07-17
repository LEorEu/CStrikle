/* CStrikle frontend */
"use strict";
const $ = (id) => document.getElementById(id);
const API = "";

let META = null, PLAYERS = [];
let soloGame = null;
let room = { ws: null, code: null, token: null, state: null, vsAi: false };

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
const COUNTRY_CN = {
  "Denmark":"丹麦","Sweden":"瑞典","Norway":"挪威","Finland":"芬兰","France":"法国",
  "Germany":"德国","Poland":"波兰","Czech Republic":"捷克","Czechia":"捷克",
  "Slovakia":"斯洛伐克","United Kingdom":"英国","Spain":"西班牙","Portugal":"葡萄牙",
  "Netherlands":"荷兰","Belgium":"比利时","Bosnia and Herzegovina":"波黑",
  "Serbia":"塞尔维亚","Croatia":"克罗地亚","Slovenia":"斯洛文尼亚","Montenegro":"黑山",
  "North Macedonia":"北马其顿","Macedonia":"马其顿","Bulgaria":"保加利亚",
  "Romania":"罗马尼亚","Hungary":"匈牙利","Austria":"奥地利","Switzerland":"瑞士",
  "Italy":"意大利","Greece":"希腊","Turkey":"土耳其","Türkiye":"土耳其",
  "Estonia":"爱沙尼亚","Latvia":"拉脱维亚","Lithuania":"立陶宛","Iceland":"冰岛",
  "Ireland":"爱尔兰","Luxembourg":"卢森堡","Malta":"马耳他","Kosovo":"科索沃",
  "Albania":"阿尔巴尼亚","Moldova":"摩尔多瓦","Russia":"俄罗斯","Ukraine":"乌克兰",
  "Belarus":"白俄罗斯","Kazakhstan":"哈萨克斯坦","Uzbekistan":"乌兹别克斯坦",
  "Kyrgyzstan":"吉尔吉斯斯坦","Armenia":"亚美尼亚","Georgia":"格鲁吉亚",
  "Azerbaijan":"阿塞拜疆","Tajikistan":"塔吉克斯坦","United States":"美国",
  "Canada":"加拿大","Mexico":"墨西哥","Brazil":"巴西","Argentina":"阿根廷",
  "Chile":"智利","Uruguay":"乌拉圭","Peru":"秘鲁","Colombia":"哥伦比亚",
  "Venezuela":"委内瑞拉","Ecuador":"厄瓜多尔","Paraguay":"巴拉圭","Bolivia":"玻利维亚",
  "Guatemala":"危地马拉","Costa Rica":"哥斯达黎加","Dominican Republic":"多米尼加",
  "China":"中国","Mongolia":"蒙古","South Korea":"韩国","Japan":"日本",
  "Taiwan":"中国台湾","Hong Kong":"中国香港","Singapore":"新加坡","Malaysia":"马来西亚",
  "Indonesia":"印尼","Thailand":"泰国","Vietnam":"越南","Philippines":"菲律宾",
  "India":"印度","Pakistan":"巴基斯坦","Bangladesh":"孟加拉国","Sri Lanka":"斯里兰卡",
  "Nepal":"尼泊尔","Myanmar":"缅甸","Laos":"老挝","Cambodia":"柬埔寨","Macau":"中国澳门",
  "Australia":"澳大利亚","New Zealand":"新西兰","Israel":"以色列","Jordan":"约旦",
  "Lebanon":"黎巴嫩","Saudi Arabia":"沙特","United Arab Emirates":"阿联酋",
  "Qatar":"卡塔尔","Kuwait":"科威特","Iraq":"伊拉克","Iran":"伊朗","Egypt":"埃及",
  "South Africa":"南非","Morocco":"摩洛哥","Tunisia":"突尼斯","Algeria":"阿尔及利亚",
  "Nigeria":"尼日利亚","Kenya":"肯尼亚",
};
const cnCountry = (c) => COUNTRY_CN[c] || c || "?";

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
    throw new Error(msg);
  }
  return r.json();
}
function go(view) {
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  $("view-" + view).classList.remove("hidden");
  if (view !== "room" && room.ws) { room.ws.close(); room.ws = null; }
}

/* ---------------- settings widget ---------------- */
function renderSettings(container, { withGuesses = true, withTimer = false } = {}) {
  const el = typeof container === "string" ? $(container) : container;
  const regions = META ? META.regions : [];
  el.innerHTML = `
  <div class="settings">
    <div class="srow"><b>难度</b>
      <span class="seg" data-k="difficulty">
        <button data-v="easy">简单·热门</button>
        <button data-v="medium" class="on">常规</button>
        <button data-v="hard">困难·全部</button>
      </span>
      <span class="dim pool-hint"></span>
    </div>
    <div class="srow"><b>赛区</b>
      <span class="regions">${regions.map(r =>
        `<span class="tag" data-r="${r}">${REGION_CN[r] || r}</span>`).join(" ")}</span>
      <span class="dim">(不选=全部)</span>
    </div>
    <div class="srow"><b>范围</b>
      <label class="chk" style="margin:0"><input type="checkbox" class="active-only">仅现役</label>
      <span>Major年代
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
      <span class="dim">时间到还没人猜中就算平局</span>
    </div>` : ""}
  </div>`;
  const seg = el.querySelector(".seg");
  const hint = el.querySelector(".pool-hint");
  const updHint = () => {
    if (!META) return;
    const d = seg.querySelector(".on").dataset.v;
    hint.textContent = `候选约 ${META.pool_sizes[d]} 人`;
  };
  seg.querySelectorAll("button").forEach(b => b.onclick = () => {
    seg.querySelectorAll("button").forEach(x => x.classList.remove("on"));
    b.classList.add("on"); updHint();
  });
  el.querySelectorAll(".tag").forEach(t => t.onclick = () => t.classList.toggle("on"));
  updHint();
  return () => ({
    difficulty: seg.querySelector(".on").dataset.v,
    regions: [...el.querySelectorAll(".tag.on")].map(t => t.dataset.r),
    active_only: el.querySelector(".active-only").checked,
    year_from: +el.querySelector(".yr-from").value || null,
    year_to: +el.querySelector(".yr-to").value || null,
    max_guesses: withGuesses ? +el.querySelector(".max-guesses").value : 8,
    game_seconds: withTimer ? (+el.querySelector(".game-seconds").value || null) : null,
  });
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
        ${flagHtml(p.country, p.flag)} <b>${esc(p.nickname)}</b>
        <span class="who">${esc(p.real_name || "")}${p.team ? " · " + esc(p.team) : ""}</span>
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
      if (vis && sel >= 0) { close(); onPick(items[sel]); }
      else if (vis && items.length) { close(); onPick(items[0]); }
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
const HEAD = ["选手", "国籍", "战队", "年龄", "位置", "MAJOR"];
function flagHtml(country, flagPath) {
  if (flagPath) return `<img class="fl" src="${flagPath}" alt="${esc(country)}" title="${esc(country)}">`;
  const f = flag(country);
  return f ? `<span class="fl-txt">${f}</span>` : "";
}
function avaHtml(p) {
  if (p.photo) return `<img class="ava" src="${p.photo}" alt="" loading="lazy">`;
  const init = esc((p.nickname || "?").slice(0, 2).toUpperCase());
  return `<div class="ava fallback">${init}</div>`;
}
function rowHtml(row) {
  const p = row.player, byKey = {};
  row.cells.forEach(x => byKey[x.key] = x);
  const arrow = (x) => x.dir === "up" ? ' <span class="arrow">▲</span>' :
                       x.dir === "down" ? ' <span class="arrow">▼</span>' : "";
  const n = byKey.nationality, t = byKey.team, a = byKey.age,
        r = byKey.role, m = byKey.majors;
  const tlogo = p.team_logo && t.value === (p.team || "无战队")
    ? `<img class="tlogo${p.team_logo.includes("_lm.") ? " chip" : ""}" src="${p.team_logo}" alt="" loading="lazy">` : "";
  return `<div class="grow">
    <div class="cell name">${avaHtml(p)}
      <span><span class="nick">${esc(p.nickname)}</span>
      <span class="small">${esc(p.real_name || "")}</span></span></div>
    <div class="cell ${n.state}" title="${esc(n.value)}"><span class="row1">${flagHtml(n.value, p.flag)} ${esc(cnCountry(n.value))}</span>
      <span class="small">${REGION_CN[n.extra] || ""}</span></div>
    <div class="cell ${t.state}"><span class="row1">${tlogo}<span>${esc(t.value)}</span></span></div>
    <div class="cell ${a.state}"><span class="num">${a.value}${arrow(a)}</span></div>
    <div class="cell ${r.state}">${esc(r.value)}</div>
    <div class="cell ${m.state}"><span class="num">${m.value}${arrow(m)}</span></div>
  </div>`;
}
function renderGrid(el, rows) {
  el.innerHTML = `<div class="grow header">${HEAD.map(h => `<div>${h}</div>`).join("")}</div>`
    + rows.map(rowHtml).join("");
}
function pipsHtml(used, total) {
  let h = '<span class="pips">';
  for (let i = 0; i < total; i++)
    h += `<span class="pip${i < used ? " used" : ""}"></span>`;
  return h + "</span>";
}
function answerCard(a) {
  const photo = a.photo ? `<img class="photo" src="${a.photo}" alt="">`
    : `<div class="photo fallback">${esc(a.nickname.slice(0, 2).toUpperCase())}</div>`;
  const tlogo = a.team_logo ? `<img class="tlogo${a.team_logo.includes("_lm.") ? " chip" : ""}" src="${a.team_logo}" alt="">` : "";
  return `<div class="answer-card">${photo}
    <div>
      <div class="a-name">${flagHtml(a.country, a.flag)} ${esc(a.nickname)}</div>
      <div class="a-real">${esc(a.real_name || "")}</div>
      <div class="a-facts">
        <span>${esc(cnCountry(a.country))} · ${REGION_CN[a.region] || a.region}</span>
        <span><b>${a.age ?? "?"}</b> 岁</span>
        <span>${tlogo}${esc(a.team || "无战队")}</span>
        <span>${esc(a.role)}</span>
        <span><b>${a.majors_count}</b> 次 Major</span>
      </div>
    </div>
  </div>`;
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
    ? `📅 每日挑战 <b>${new Date().toISOString().slice(0, 10)}</b>` : "♾️ 无限模式";
  $("game-remaining").innerHTML = pipsHtml(g.guesses.length, g.settings.max_guesses);
  $("game-pool").textContent = `候选 ${g.pool_size} 人`;
  renderGrid($("grid"), g.guesses);
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
  const g = soloGame;
  const map = { green: "🟩", yellow: "🟨", gray: "⬛" };
  const lines = g.guesses.map(r => r.cells.map(c => map[c.state]).join(""));
  const txt = `CStrikle ${new Date().toISOString().slice(0, 10)} ${g.status === "won" ? g.guesses.length : "X"}/${g.settings.max_guesses}\n` + lines.join("\n");
  navigator.clipboard.writeText(txt).then(() => toast("已复制,发给朋友吧"));
}

/* ---------------- versus ---------------- */
let getRoomSettings = null;
async function createRoom() {
  const vsAi = $("vs-ai").checked;
  const settings = getRoomSettings();
  try {
    const r = await api("/api/room", { method: "POST", body: {
      name: $("host-name").value.trim() || "玩家1",
      settings, vs_ai: vsAi, ai_speed: $("ai-speed").value,
    }});
    localStorage.setItem("cstrikle_name", $("host-name").value.trim());
    enterRoom(r.code, r.token, vsAi);
    if (!vsAi) toast(`房间码 ${r.code},发给朋友让他加入`, 6000);
  } catch (e) { toast(e.message); }
}
async function joinRoom() {
  const code = $("join-code").value.trim().toUpperCase();
  if (code.length < 4) { toast("输入 4 位房间码"); return; }
  try {
    const r = await api(`/api/room/${code}/join`, { method: "POST", body: {
      name: $("join-name").value.trim() || "玩家2",
    }});
    localStorage.setItem("cstrikle_name", $("join-name").value.trim());
    enterRoom(r.code, r.token, false);
  } catch (e) { toast(e.message); }
}
function enterRoom(code, token, vsAi) {
  room = { ws: null, code, token, state: null, vsAi };
  go("room");
  $("room-code").textContent = code;
  $("room-guess-input").value = "";
  $("chat-log").innerHTML = "";
  $("btn-transcript").classList.add("hidden");
  $("room-result").classList.add("hidden");
  $("room-result").dataset.spoiler = "";
  $("opp-reveal-main").innerHTML = "";
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
  if (msg.type === "state") { room.state = msg; renderRoom(); }
  else if (msg.type === "chat") addChat(msg);
  else if (msg.type === "error") toast(msg.message);
  else if (msg.type === "ai_status") {
    const el = $("ai-status");
    if (msg.state === "idle") el.classList.add("hidden");
    else {
      el.classList.remove("hidden");
      el.textContent = msg.state === "searching" ? "AI 正在上网搜资料…" : "AI 正在思考…";
    }
  }
}
let turnTimerInt = null;
function renderRoom() {
  const s = room.state;
  const you = s.you, opp = s.opponent;
  const justEnded = s.status === "over" && room.lastStatus === "playing";
  room.lastStatus = s.status;

  // 整局限时倒计时
  clearInterval(turnTimerInt);
  const tt = $("turn-timer");
  if (s.status === "playing" && s.deadline) {
    const offset = (s.now || Date.now() / 1000) - Date.now() / 1000;
    const upd = () => {
      const left = Math.max(0, Math.round(s.deadline - offset - Date.now() / 1000));
      tt.textContent = `⏱ ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
      tt.classList.toggle("urgent", left <= 30);
    };
    upd();
    turnTimerInt = setInterval(upd, 500);
    tt.classList.remove("hidden");
  } else tt.classList.add("hidden");
  $("room-status").textContent = s.status === "waiting" ? "等待对手加入…"
    : s.status === "playing" ? "对局进行中" : "对局结束";
  $("room-remaining").innerHTML = pipsHtml(you.rows.length, s.settings.max_guesses);
  renderGrid($("room-grid"), you.rows);
  $("room-guess-input").disabled = s.status !== "playing" || you.status !== "playing";

  // opponent panel
  if (opp) {
    $("opp-name").textContent = `${opp.is_ai ? "🤖 " : "🧑 "}${opp.name}`;
    $("opp-remaining").textContent = `对手剩余次数 ${opp.remaining}`;
    const MINI = { nationality: "国", team: "队", age: "龄", role: "位", majors: "M" };
    $("opp-grid").innerHTML = opp.colors.map((r, i) => {
      const hit = r.every(c => c.state === "green");
      return `<div class="mini-row${hit ? " hit" : ""}"><span class="mini-idx">${i + 1}</span>${r.map(c =>
        `<div class="mini-cell ${c.state}">${MINI[c.key] || ""}${c.dir === "up" ? "▲" : c.dir === "down" ? "▼" : ""}</div>`
      ).join("")}${hit ? '<span class="mini-hit">✔</span>' : ""}</div>`;
    }).join("");
  } else {
    $("opp-name").textContent = "等待对手…";
    $("opp-grid").innerHTML = ""; $("opp-remaining").textContent = "";
  }

  // chat backlog (state carries recent history)
  if (s.chat && !$("chat-log").childElementCount) s.chat.forEach(addChat);

  const res = $("room-result");
  if (s.status === "over") {
    res.dataset.spoiler = "";
    res.classList.remove("hidden");
    const iWon = s.winner === you.name;
    res.className = "result " + (iWon ? "win" : s.winner === "draw" ? "" : "lose");
    res.innerHTML = `<div class="verdict">${s.winner === "draw"
        ? "DRAW — 平局,谁都没猜出来"
        : iWon ? "VICTORY — 你先猜中了" : `DEFEAT — ${esc(s.winner)} 先猜中了`}</div>`
      + answerCard(s.answer);
    if (opp && opp.is_ai) $("btn-transcript").classList.remove("hidden");
    const rev = $("opp-reveal-main");
    if (s.opponent_rows && s.opponent_rows.length) {
      rev.innerHTML = `<h3 class="reveal-title">对手 ${esc(opp ? opp.name : "")} 的猜测</h3>`;
      const div = document.createElement("div");
      div.className = "grid";
      renderGrid(div, s.opponent_rows);
      rev.appendChild(div);
    } else rev.innerHTML = "";
    $("ai-status").classList.add("hidden");
    if (justEnded) {
      const iWon = s.winner === you.name;
      const kind = iWon ? "win" : s.winner === "draw" ? "draw" : "lose";
      const title = iWon ? "VICTORY" : s.winner === "draw" ? "DRAW" : "DEFEAT";
      const sub = iWon ? "你先猜中了" : s.winner === "draw" ? "谁都没猜出来"
        : `${s.winner} 先猜中了`;
      const btns = (opp && opp.is_ai
        ? `<button class="primary" onclick="overlayTranscript()">🧠 看 AI 的思考回放</button>` : "")
        + `<button onclick="closeEndOverlay()">关闭</button>`;
      setTimeout(() => showEndOverlay(kind, title, sub, s.answer, btns), 700);
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
            <details><summary>👀 偷看谜底(剧透警告)</summary>${answerCard(s.answer_spoiler)}</details>
          </div>`;
      }
    } else { res.classList.add("hidden"); res.dataset.spoiler = ""; }
    $("opp-reveal-main").innerHTML = "";
  }
}
function addChat(m) {
  const log = $("chat-log");
  const div = document.createElement("div");
  const isAi = m.from && m.from.startsWith("AI");
  div.className = m.from === "系统" ? "c-sys" : isAi ? "c-ai" : "";
  div.innerHTML = m.from === "系统" ? esc(m.text)
    : `<span class="c-from">${esc(m.from)}:</span> ${esc(m.text)}`;
  log.appendChild(div);
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
  if (room.ws) { room.ws.close(); room.ws = null; }
  go("versus-lobby");
}
async function showTranscript() {
  try {
    const t = await api(`/api/room/${room.code}/transcript`, {
      headers: { "X-Room-Token": room.token },
    });
    $("transcript-model").textContent = t.model || "";
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
    case "reasoning": return `<div class="ev"><details><summary>内部推理(reasoning)</summary><pre>${esc(e.text)}</pre></details></div>`;
    case "thinking": return `<div class="ev ev-thinking">${esc(e.text)}</div>`;
    case "search": return `<div class="ev ev-search">🔍 搜索:「${esc(e.query)}」</div>`;
    case "search_result": return `<div class="ev"><details><summary>搜索结果</summary><pre>${esc(e.text)}</pre></details></div>`;
    case "say": return `<div class="ev ev-say">💬 垃圾话:${esc(e.text)}</div>`;
    case "guess": return `<div class="ev ev-guess">🎯 提交猜测:${esc(e.name)}</div>`;
    case "guess_rejected": return `<div class="ev ev-rejected">❌ 想猜 ${esc(e.name)} 被驳回:${esc(e.reason)}</div>`;
    case "forced_guess": return `<div class="ev ev-rejected">⚠️ ${esc(e.reason)}:${esc(e.name)}</div>`;
    default: return "";
  }
}

/* ---------------- init ---------------- */
async function init() {
  try {
    [META, PLAYERS] = await Promise.all([api("/api/meta"), api("/api/players")]);
    $("meta-info").textContent =
      `选手库 ${META.player_count} 人 · 更新于 ${META.db_generated_at.slice(0, 10)}`
      + (META.ai_enabled ? ` · AI: ${META.ai_model}` : " · AI 未配置");
    if (!META.ai_enabled) $("vs-ai").disabled = true;
  } catch (e) { toast("加载选手库失败: " + e.message); }
  getRoomSettings = renderSettings("settings-room", { withGuesses: true, withTimer: true });
  attachSuggest($("guess-input"), $("suggest"), soloGuess);
  attachSuggest($("room-guess-input"), $("room-suggest"), roomGuess);
  $("vs-ai").addEventListener("change", () =>
    $("ai-speed-row").classList.toggle("hidden", !$("vs-ai").checked));
  $("chat-text").addEventListener("keydown", e => { if (e.key === "Enter") sendChat(); });
  const saved = localStorage.getItem("cstrikle_name") || "";
  $("host-name").value = saved; $("join-name").value = saved;
}
init();
