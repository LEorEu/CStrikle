/* CSTRIKLE 管理页:原生 JS,无构建。 */
"use strict";
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const cnCountry = c => (typeof COUNTRY_CN === "object" && COUNTRY_CN[c]) || c || "?";
/* 国籍必须落在 COUNTRY_CN/REGION 的键上,拼错会同时打掉国旗和赛区,
   所以只给下拉、不给自由输入(线上出现过手打的 "russia")。 */
const countryOptions = cur => ["", ...Object.keys(COUNTRY_CN)]
  .map(c => `<option value="${esc(c)}" ${c === cur ? "selected" : ""}>${
    c ? esc(cnCountry(c)) + " · " + esc(c) : "(未填)"}</option>`).join("");
const STATUS_OPTIONS = ["Active", "Inactive", "Retired"];

let TOKEN = localStorage.getItem("csk_admin_token") || "";
let fbCache = [];          // 反馈列表缓存(渲染筛选用)

/* ------------------------------------------------------------ api */
async function api(path, opts = {}) {
  const r = await fetch("/api/admin" + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Token": TOKEN,
      ...(opts.headers || {}),
    },
  });
  if (r.status === 401) { showLogin("口令不正确或已失效"); throw new Error("unauthorized"); }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d.detail || ("HTTP " + r.status));
  }
  return r.json();
}

let toastTimer = null;
function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = bad ? "bad" : "";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 2600);
}

/* ---------------------------------------------------------- login */
function showLogin(err = "") {
  $("#viewMain").classList.add("hidden");
  $("#viewLogin").classList.remove("hidden");
  const e = $("#loginErr");
  e.textContent = err;
  e.classList.toggle("hidden", !err);
  $("#loginToken").focus();
}

async function enter() {
  let meta;
  try { meta = await api("/ping"); }
  catch (err) { if (err.message !== "unauthorized") showLogin(err.message); return; }
  localStorage.setItem("csk_admin_token", TOKEN);
  $("#viewLogin").classList.add("hidden");
  $("#viewMain").classList.remove("hidden");
  renderMeta(meta);
  loadFeedback();
}

function renderMeta(m) {
  $("#metaDb").textContent = "数据 " + (m.db_generated_at || "?").slice(0, 10);
  $("#metaCount").textContent = `${m.player_count} 人 / 谜底池 ${m.answer_player_count}`;
}

$("#loginForm").addEventListener("submit", ev => {
  ev.preventDefault();
  TOKEN = $("#loginToken").value.trim();
  if (TOKEN) enter();
});
$("#btnLogout").addEventListener("click", () => {
  localStorage.removeItem("csk_admin_token");
  TOKEN = "";
  showLogin();
});
$("#btnReload").addEventListener("click", async () => {
  $("#btnReload").disabled = true;
  try {
    const m = await api("/reload", { method: "POST" });
    renderMeta(m);
    toast(`已重载:${m.player_count} 名选手`);
  } catch (e) { toast("重载失败: " + e.message, true); }
  finally { $("#btnReload").disabled = false; }
});

/* ----------------------------------------------------------- tabs */
const TABS = ["feedback", "players", "health", "update", "hltv"];
function switchTab(tab) {
  $$(".admin-tabs button").forEach(x =>
    x.classList.toggle("on", x.dataset.tab === tab));
  TABS.forEach(t =>
    $("#tab-" + t).classList.toggle("hidden", t !== tab));
  if (tab === "feedback") loadFeedback();
  if (tab === "health") loadHealth();
  if (tab === "update") loadStaging();
  if (tab === "hltv") loadHltv();
  if (tab === "players" && !$("#pResults").innerHTML) doSearch();
}

/* ---------------------------------------------------------- 弹窗
   <dialog> 原生就有遮罩、ESC 关闭和焦点锁定,自己拿 div 拼一套只会更差。 */
function openModal(dlg) { if (!dlg.open) dlg.showModal(); }
$$("dialog.admin-modal [data-close]").forEach(b =>
  b.addEventListener("click", () => b.closest("dialog").close()));
/* 故意不做「点遮罩关闭」:这两个弹窗里都是填了一半的表单(reason 还是必填),
   一次手滑就得重打一遍。关闭走 ✕ / 取消 / ESC 三条明确的路。 */
$$(".admin-tabs button").forEach(b =>
  b.addEventListener("click", () => switchTab(b.dataset.tab)));

function gotoPlayerTab(page) {
  switchTab("players");
  openEditor(page);
}

/* ------------------------------------------------------- feedback */
async function loadFeedback() {
  try {
    const d = await api("/feedback");
    fbCache = d.entries;
    const badge = $("#fbBadge");
    badge.textContent = d.open_count;
    badge.classList.toggle("hidden", !d.open_count);
    renderFeedback();
  } catch (e) { toast("反馈加载失败: " + e.message, true); }
}

function renderFeedback() {
  const showResolved = $("#fbShowResolved").checked;
  const list = fbCache.filter(e => showResolved || !e.resolved);
  if (!list.length) {
    $("#fbList").innerHTML = `<p class="dim">没有${showResolved ? "" : "待处理的"}反馈。</p>`;
    return;
  }
  // 按选手分组,同组内保持时间序(新在前)
  const groups = new Map();
  for (const e of list) {
    const key = e.page || "__general__";
    if (!groups.has(key)) groups.set(key, { player: e.player, page: e.page, items: [] });
    groups.get(key).items.push(e);
  }
  let html = "";
  for (const g of groups.values()) {
    const p = g.player;
    const head = p
      ? `${p.photo ? `<img src="${esc(p.photo)}" alt="">` : ""}
         <span class="nick">${esc(p.nickname)}</span>
         <span class="dim">${esc(p.team || "自由身")} · ${esc(p.role)}</span>
         <button class="mini-btn" data-edit="${esc(g.page)}">编辑该选手</button>`
      : (g.page
         ? `<span class="nick">${esc(g.page)}</span><span class="dim">(库中未找到)</span>`
         : `<span class="nick">整体反馈</span>`);
    const items = g.items.map(e => `
      <div class="fb-item ${e.resolved ? "resolved" : ""}">
        <span class="when">${esc((e.ts || "").replace("T", " ").slice(0, 16))}<br>${esc(e.ip)}</span>
        <div class="msg">${esc(e.message)}
          ${e.context ? `<div class="dim">场景: ${esc(e.context)}</div>` : ""}
          ${e.note ? `<div class="note">备注: ${esc(e.note)}</div>` : ""}
        </div>
        <div class="fb-actions">
          <button class="mini-btn" data-fid="${esc(e.id)}" data-resolved="${e.resolved ? 0 : 1}">
            ${e.resolved ? "重开" : "已处理"}</button>
        </div>
      </div>`).join("");
    html += `<div class="fb-group"><div class="fb-head">${head}</div>${items}</div>`;
  }
  $("#fbList").innerHTML = html;
  $$("#fbList [data-edit]").forEach(b =>
    b.addEventListener("click", () => gotoPlayerTab(b.dataset.edit)));
  $$("#fbList [data-fid]").forEach(b => b.addEventListener("click", async () => {
    const resolved = b.dataset.resolved === "1";
    let note = "";
    if (resolved) {
      note = prompt("处理备注(可留空):", "") ?? "";
    }
    try {
      await api(`/feedback/${b.dataset.fid}/state`, {
        method: "POST", body: JSON.stringify({ resolved, note }),
      });
      loadFeedback();
    } catch (e) { toast("更新失败: " + e.message, true); }
  }));
}
$("#fbShowResolved").addEventListener("change", renderFeedback);
$("#fbRefresh").addEventListener("click", loadFeedback);

/* -------------------------------------------------------- players */
const PAGE_SIZE = 50;
let pOffset = 0;                 // 当前页在结果里的起点
let searchTimer = null;
/* 搜索词一变就回到第一页,否则「翻到第 8 页再改词」会落在空页上 */
$("#pSearch").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => doSearch(0), 250);
});
$("#pSearch").addEventListener("keydown", ev => { if (ev.key === "Enter") doSearch(0); });

async function doSearch(offset = pOffset) {
  const q = $("#pSearch").value.trim();
  try {
    // 照片走 loading="lazy",翻页时不会一次并发几十个图片请求。
    const d = await api(`/players?q=${encodeURIComponent(q)}` +
                        `&limit=${PAGE_SIZE}&offset=${Math.max(0, offset)}`);
    pOffset = d.offset;
    if (!d.players.length) {
      $("#pResults").innerHTML = `<p class="dim">没有匹配的选手。</p>`;
      $("#pPager").innerHTML = "";
      return;
    }
    $("#pResults").innerHTML = `
      <p class="dim p-count">${q ? `匹配 ${d.total} 人` : `全部 ${d.total} 人`}
        · 第 ${pOffset + 1}–${pOffset + d.players.length} 条 · 按名气排序</p>
      <table class="p-table">
        <tr><th></th><th>ID</th><th>姓名</th><th>国籍</th><th>战队</th>
            <th>位置</th><th>年龄</th><th>Major</th><th></th></tr>
        ${d.players.map(p => `
          <tr class="row" data-page="${esc(p.page)}">
            <td>${p.photo ? `<img src="${esc(p.photo)}" alt="" loading="lazy">` : ""}</td>
            <td><b>${esc(p.nickname)}</b></td>
            <td class="dim">${esc(p.real_name)}</td>
            <td>${esc(cnCountry(p.country))}</td>
            <td>${esc(p.team || "自由身")}</td>
            <td>${esc(p.role)}</td>
            <td>${p.age ?? "?"}</td>
            <td>${p.majors_count}</td>
            <td>${p.manual ? `<span class="tag-manual">人工</span>` : ""}
                ${p.has_override ? `<span class="tag-ov">override</span>` : ""}
                ${p.game_ready ? "" : `<span class="tag-nr">非谜底</span>`}</td>
          </tr>`).join("")}
      </table>`;
    $$("#pResults tr.row").forEach(tr =>
      tr.addEventListener("click", () => openEditor(tr.dataset.page)));
    renderPager(d.total);
  } catch (e) { toast("搜索失败: " + e.message, true); }
}

function renderPager(total) {
  const pages = Math.ceil(total / PAGE_SIZE);
  const cur = Math.floor(pOffset / PAGE_SIZE);
  if (pages <= 1) { $("#pPager").innerHTML = ""; return; }
  $("#pPager").innerHTML = `
    <button class="mini-btn" data-to="${pOffset - PAGE_SIZE}"
      ${cur === 0 ? "disabled" : ""}>← 上一页</button>
    <span class="dim">第 ${cur + 1} / ${pages} 页</span>
    <button class="mini-btn" data-to="${pOffset + PAGE_SIZE}"
      ${cur >= pages - 1 ? "disabled" : ""}>下一页 →</button>`;
  $$("#pPager button").forEach(b => b.addEventListener("click", () => {
    doSearch(Number(b.dataset.to));
    $("#pResults").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
}

/* ------------------------------------------------ 人工新增选手
   写 data/manual/players_manual.json,不碰 players.json——直接塞进生成物
   的话下一次整库重建就会把人冲掉(MachineWJQ 的教训)。 */
const ROLE_TAGS = ["igl", "awp", "rifle", "entry", "lurker", "support",
                   "coach", "analyst", "caster"];

function newPlayerForm(rec = null) {
  const v = rec || {};
  const box = $("#pNew");
  box.innerHTML = `
    <form id="mForm" class="m-form">
      <div class="m-title">${rec ? `编辑人工选手 <code>${esc(v.page)}</code>`
                                 : "新增选手(人工层)"}</div>
      <div class="m-grid">
        <label>ID <input name="nickname" required value="${esc(v.nickname ?? "")}"></label>
        <label>page(主键,留空取 ID)
          <input name="page" value="${esc(v.page ?? "")}" ${rec ? "readonly" : ""}></label>
        <label>真实姓名 <input name="real_name" value="${esc(v.real_name ?? "")}"></label>
        <label>国籍(定赛区与国旗)
          <select name="country">${countryOptions(v.country ?? "")}</select></label>
        <label>生日 <input name="birth_date" value="${esc(v.birth_date ?? "")}" placeholder="YYYY-MM-DD"></label>
        <label>战队 <input name="team" value="${esc(v.team ?? "")}"></label>
        <label>状态
          <select name="status">${STATUS_OPTIONS.map(o =>
            `<option ${(v.status ?? "Active") === o ? "selected" : ""}>${o}</option>`).join("")}</select></label>
        <label>位置
          <select name="game_role">
            ${["", "IGL", "AWPer", "Rifler", "Coach"].map(r =>
              `<option ${v.game_role === r ? "selected" : ""}>${r}</option>`).join("")}
          </select></label>
        <label>Major 次数
          <input name="majors_count" type="number" min="0" value="${v.majors_count ?? 0}"></label>
      </div>
      <div class="m-roles">原始 roles 标签:
        ${ROLE_TAGS.map(r => `<label class="rt"><input type="checkbox" name="roles" value="${r}"
          ${(v.roles || []).includes(r) ? "checked" : ""}>${r}</label>`).join("")}
      </div>
      <label class="dim"><input type="checkbox" name="in_blast_pool"
        ${v.in_blast_pool ? "checked" : ""}> 计入 blast 现役名单(影响难度分层)</label>
      <div class="ed-reason">
        <textarea name="reason" placeholder="reason(必填):加这个人的依据/出处">${esc(v.manual_reason ?? "")}</textarea>
      </div>
      <p class="dim m-hint">进谜底池需要:ID + 国籍 + 生日 + 位置 四项齐全;缺任意一项只能被搜到,不会被抽中。</p>
      <div class="ed-btns">
        <button type="submit" class="save">${rec ? "保存修改并重载" : "创建并重载"}</button>
        <button type="button" class="mini-btn" id="mCancel">取消</button>
      </div>
    </form>`;
  openModal($("#dlgNew"));

  $("#mCancel").addEventListener("click", () => $("#dlgNew").close());
  $("#mForm").addEventListener("submit", async ev => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    const body = {
      nickname: (f.get("nickname") || "").trim(),
      page: (f.get("page") || "").trim(),
      real_name: (f.get("real_name") || "").trim(),
      country: (f.get("country") || "").trim(),
      birth_date: (f.get("birth_date") || "").trim(),
      team: (f.get("team") || "").trim(),
      status: f.get("status") || "Active",
      game_role: f.get("game_role") || "",
      roles: f.getAll("roles"),
      majors_count: Number(f.get("majors_count") || 0),
      in_blast_pool: !!f.get("in_blast_pool"),
      reason: (f.get("reason") || "").trim(),
    };
    if (!body.reason) { toast("必须填写 reason", true); return; }
    try {
      const d = rec
        ? await api("/manual/" + encodeURIComponent(v.page),
                    { method: "PUT", body: JSON.stringify(body) })
        : await api("/manual", { method: "POST", body: JSON.stringify(body) });
      renderMeta(await api("/reload", { method: "POST" }));
      $("#dlgNew").close();
      toast(rec ? "已保存并重载" : "已新增并重载");
      doSearch();
      openEditor(d.page);
    } catch (e) { toast((rec ? "保存" : "新增") + "失败: " + e.message, true); }
  });
}
$("#pNewBtn").addEventListener("click", () => newPlayerForm());

/* 头像上传:base64 走 JSON,服务端只校验魔数和大小(生产镜像没有 Pillow)。
   对所有选手生效,人工照片优先级高于爬取的图。 */
async function uploadPhoto(page, file) {
  const data = await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = () => rej(new Error("读取文件失败"));
    fr.readAsDataURL(file);
  });
  try {
    await api(`/players/${encodeURIComponent(page)}/photo`,
              { method: "PUT", body: JSON.stringify({ data, filename: file.name }) });
    renderMeta(await api("/reload", { method: "POST" }));
    toast("照片已更新");
    doSearch();
    openEditor(page);
  } catch (e) { toast("上传失败: " + e.message, true); }
}

async function openEditor(page) {
  let d;
  try { d = await api("/players/" + encodeURIComponent(page)); }
  catch (e) { toast("加载选手失败: " + e.message, true); return; }
  const ef = d.effective, sc = d.scraped, ov = d.override || {};

  const roleSel = (name, values, cur) => `
    <select name="${name}">
      <option value="">(不覆盖)</option>
      ${values.map(v => `<option ${cur === v ? "selected" : ""}>${v}</option>`).join("")}
    </select>`;

  $("#pEditor").innerHTML = `
    <div class="ed-head">
      ${ef.photo ? `<img class="photo" src="${esc(ef.photo)}" alt="">` : ""}
      <div class="who">
        <div class="nick">${esc(ef.nickname)}</div>
        <div class="real">${esc(ef.real_name)} · ${esc(cnCountry(ef.country))} · ${esc(ef.region || "?")}</div>
        <div class="dim">page: ${esc(ef.page)}</div>
      </div>
      <div class="facts">
        Major ${ef.majors_count} 次 · ${ef.game_ready ? "谜底池内" : "不在谜底池"}<br>
        原始 roles: ${esc((ef.roles || []).join(", ") || "无")}<br>
        blast 名单: ${sc.in_blast_pool ? "是" : "否"}
      </div>
    </div>
    ${ef.manual ? `<div class="ed-hint">这是人工新增的选手 —— 改资料请用下方的
      <b>编辑资料</b>(写人工记录本身)。下面这张 override 表是叠加在记录之上的,
      同一个字段改两处只会更乱。</div>` : ""}
    ${d.override ? `<div class="ov-now">当前 override: <code>${esc(JSON.stringify(d.override))}</code></div>` : ""}
    <form id="ovForm">
    <table class="ed-grid">
      <tr><th>字段</th><th>爬取值</th><th>生效值</th><th>override(留空 = 不覆盖)</th></tr>
      <tr><td class="f">战队</td>
          <td class="scraped">${esc(sc.team ?? "")}</td><td>${esc(ef.team || "自由身")}</td>
          <td><input name="team" value="${esc(ov.team ?? "")}" placeholder="填空字符串需勾选下方"></td></tr>
      <tr><td class="f">状态</td>
          <td class="scraped">${esc(sc.status ?? "")}</td><td>${esc(ef.status || "")}</td>
          <td>${roleSel("status", STATUS_OPTIONS, ov.status)}</td></tr>
      <tr><td class="f">位置</td>
          <td class="scraped">${esc((sc.roles || []).join(", "))}</td><td>${esc(ef.role)}</td>
          <td>${roleSel("game_role", ["IGL", "AWPer", "Rifler", "Coach"], ov.game_role)}</td></tr>
      <tr><td class="f">选手期位置</td>
          <td class="scraped">-</td><td class="dim">教练/职务人员回退用</td>
          <td>${roleSel("played_role", ["IGL", "AWPer", "Rifler"], ov.played_role)}</td></tr>
      <tr><td class="f">生日</td>
          <td class="scraped">${esc(sc.birth_date ?? "")}</td>
          <td>${esc(ef.birth_date || "")}(${ef.age ?? "?"} 岁)</td>
          <td><input name="birth_date" value="${esc(ov.birth_date ?? "")}" placeholder="YYYY-MM-DD"></td></tr>
    </table>
    <label class="dim" style="display:block;margin-top:8px">
      <input type="checkbox" name="team_empty" ${ov.team === "" ? "checked" : ""}>
      覆盖战队为空(强制自由身,如 olof 挂名 FaZe 直播的情况)
    </label>
    <div class="ed-reason">
      <textarea name="reason" placeholder="reason(必填):修改依据,例如 Liquipedia/HLTV 链接或说明">${esc(ov.reason ?? "")}</textarea>
    </div>
    <div class="ed-btns">
      <button type="submit" class="save">保存 override 并重载</button>
      ${d.override ? `<button type="button" class="del" id="ovDel">删除 override</button>` : ""}
      <span class="dim">只写 player_overrides.json,scraper 重跑不会丢</span>
    </div>
    </form>
    <div class="ed-photo">
      <label class="mini-btn as-label">上传照片
        <input type="file" id="phFile" accept="image/jpeg,image/png,image/webp" hidden></label>
      ${ef.manual_photo ? `<button type="button" class="mini-btn" id="phDel">删除人工照片</button>` : ""}
      <span class="dim">存进人工层(≤2MB,JPEG/PNG/WebP),优先于爬取的图;建议 600px 源图</span>
    </div>
    ${ef.manual ? `
    <div class="ed-manual">
      <span class="tag-manual">人工新增</span>
      <button type="button" class="mini-btn" id="mEdit">编辑资料</button>
      <button type="button" class="del" id="mDel">删除该选手</button>
      <span class="dim">这条记录存在人工层,爬虫重建不会覆盖也不会恢复</span>
    </div>` : ""}
    <div class="ed-fb">
      <h3>该选手的反馈(${d.feedback.length})</h3>
      ${d.feedback.length ? d.feedback.map(e => `
        <div class="fb-item ${e.resolved ? "resolved" : ""}">
          <span class="when">${esc((e.ts || "").replace("T", " ").slice(0, 16))}</span>
          <div class="msg">${esc(e.message)}</div>
        </div>`).join("") : `<p class="dim">暂无</p>`}
    </div>`;
  openModal($("#dlgEditor"));
  $("#pEditor").scrollTop = 0;    // 滚动条在内层 div 上,见 admin.css

  $("#ovForm").addEventListener("submit", async ev => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    const fields = {};
    const team = f.get("team").trim();
    if (team) fields.team = team;
    else if (f.get("team_empty")) fields.team = "";
    for (const k of ["status", "game_role", "played_role", "birth_date"]) {
      const v = (f.get(k) || "").trim();
      if (v) fields[k] = v;
    }
    const reason = (f.get("reason") || "").trim();
    if (!reason) { toast("必须填写 reason", true); return; }
    if (!Object.keys(fields).length) {
      toast("上面四个字段至少改一个 —— reason 是这次改动的依据,不能单独保存", true);
      return;
    }
    try {
      await api(`/players/${encodeURIComponent(page)}/override`, {
        method: "PUT", body: JSON.stringify({ fields, reason }),
      });
      const m = await api("/reload", { method: "POST" });
      renderMeta(m);
      toast("已保存并重载");
      doSearch();               // 列表里那一行也跟着变,不用手动刷新
      openEditor(page);
    } catch (e) { toast("保存失败: " + e.message, true); }
  });
  $("#phFile").addEventListener("change", ev => {
    const file = ev.target.files[0];
    if (file) uploadPhoto(page, file);
  });
  const phDel = $("#phDel");
  if (phDel) phDel.addEventListener("click", async () => {
    if (!confirm(`删除 ${ef.nickname} 的人工照片,回到爬取的图?`)) return;
    try {
      await api(`/players/${encodeURIComponent(page)}/photo`, { method: "DELETE" });
      renderMeta(await api("/reload", { method: "POST" }));
      toast("已删除并重载");
      doSearch();
      openEditor(page);
    } catch (e) { toast("删除失败: " + e.message, true); }
  });
  const mEdit = $("#mEdit");
  if (mEdit) mEdit.addEventListener("click", () => newPlayerForm({
    page: ef.page, nickname: ef.nickname, real_name: ef.real_name,
    country: ef.country, birth_date: ef.birth_date, team: ef.team,
    game_role: ef.game_role, roles: ef.roles, majors_count: ef.majors_count,
    in_blast_pool: sc.in_blast_pool, manual_reason: sc.manual_reason,
  }));
  const mDel = $("#mDel");
  if (mDel) mDel.addEventListener("click", async () => {
    if (!confirm(`彻底删除人工选手 ${ef.nickname}?照片也会一并清掉。`)) return;
    try {
      await api("/manual/" + encodeURIComponent(page), { method: "DELETE" });
      renderMeta(await api("/reload", { method: "POST" }));
      $("#dlgEditor").close();
      toast("已删除并重载");
      doSearch();
    } catch (e) { toast("删除失败: " + e.message, true); }
  });

  const del = $("#ovDel");
  if (del) del.addEventListener("click", async () => {
    if (!confirm(`删除 ${ef.nickname} 的 override,回到纯爬取数据?`)) return;
    try {
      await api(`/players/${encodeURIComponent(page)}/override`, { method: "DELETE" });
      const m = await api("/reload", { method: "POST" });
      renderMeta(m);
      toast("已删除并重载");
      doSearch();
      openEditor(page);
    } catch (e) { toast("删除失败: " + e.message, true); }
  });
}

/* --------------------------------------------------------- health */
const H_META = {
  team_no_igl: ["现役阵容无指挥", "整队没人被标成 IGL,多半是上游漏标;按队列出全员,人工挑出该标的那个"],
  team_igl_conflict: ["同队多指挥", "同一现役阵容 2 个以上 IGL,多半是交接指挥后上游残留的旧标签"],
  missing_birth_date: ["缺生日", "无法算年龄,进不了谜底池"],
  missing_role: ["缺位置", "primary_role 无法归一化"],
  missing_photo: ["缺照片", "揭晓卡没有大图"],
  missing_country: ["缺国籍", "国籍反馈维度失效"],
  age_anomaly: ["年龄异常", "小于 14 或大于 48,多半是生日数据错误"],
  not_game_ready: ["非谜底池", "可被搜索/猜测,但不会成为谜底"],
  orphan_override: ["失效的 override", "override 以 page 名为键,上游改了页名就静默失效,人工结论会悄悄回退"],
};

/* 按队分组展示的类别:问题的单位是"一套阵容"而不是单个选手,
   平铺成一串 chip 就看不出谁和谁是一队的了。 */
const H_GROUPED = new Set(["team_no_igl", "team_igl_conflict"]);

function hChip(p) {
  return `
    <span class="chip" data-page="${esc(p.page)}">
      ${p.photo ? `<img src="${esc(p.photo)}" alt="">` : ""}
      ${esc(p.nickname)}
      <span class="dim">${esc(p.role || "")}</span>
    </span>`;
}

function hBody(key, list) {
  if (!list.length) return `<span class="dim">全部正常</span>`;
  if (key === "orphan_override") {
    // 这些条目对应不上任何选手,没有 page 可跳转,直接把键和内容摊开
    return list.map(o => `
      <div class="h-orphan">
        <code>${esc(o.key)}</code>
        <span class="dim">${esc(JSON.stringify(o.override))}</span>
      </div>`).join("");
  }
  if (!H_GROUPED.has(key)) {
    return list.map(p => `
      <span class="chip" data-page="${esc(p.page)}">
        ${p.photo ? `<img src="${esc(p.photo)}" alt="">` : ""}
        ${esc(p.nickname)}
        <span class="dim">${esc(p.team || "")}</span>
      </span>`).join("");
  }
  const teams = new Map();
  list.forEach(p => {
    const t = p.team || "—";
    if (!teams.has(t)) teams.set(t, []);
    teams.get(t).push(p);
  });
  return [...teams].map(([team, ps]) => `
    <div class="h-group">
      <span class="h-team">${esc(team)}</span>
      ${ps.map(hChip).join("")}
    </div>`).join("");
}

async function loadHealth() {
  $("#hList").innerHTML = `<p class="dim">统计中...</p>`;
  try {
    const d = await api("/health");
    $("#hList").innerHTML = Object.entries(H_META).map(([k, [title, desc]]) => {
      const list = d.categories[k] || [];
      return `
        <details class="h-sec" ${list.length && list.length <= 30 ? "open" : ""}>
          <summary><span class="cnt">${list.length}</span> ${title}
            <span class="desc">${desc}</span></summary>
          <div class="h-body">${hBody(k, list)}</div>
        </details>`;
    }).join("");
    $$("#hList .chip").forEach(c =>
      c.addEventListener("click", () => gotoPlayerTab(c.dataset.page)));
  } catch (e) { $("#hList").innerHTML = `<p class="err">加载失败: ${esc(e.message)}</p>`; }
}
$("#hRefresh").addEventListener("click", loadHealth);

/* ------------------------------------------------ update (staging) */
const FIELD_LABEL = {
  nickname: "ID", real_name: "姓名", country: "国籍", team: "战队",
  status: "状态", birth_date: "生日", roles: "位置标签",
  majors_count: "Major数", in_blast_pool: "blast名单",
};
const JOB_LABEL = { build: "完整重建", refresh: "快速刷新", images: "补齐图片" };
let jobTimer = null;
let jobWasRunning = false;

async function loadStaging() {
  try {
    const d = await api("/staging");
    renderJob(d.job);
    renderStaging(d);
  } catch (e) { toast("staging 加载失败: " + e.message, true); }
}

function renderJob(job) {
  const box = $("#jobBox");
  clearTimeout(jobTimer);
  if (!job || (!job.running && job.returncode === null)) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");
  const state = job.running ? " · 运行中..."
    : (job.returncode === 0 ? " · 完成" : ` · 失败(exit ${job.returncode})`);
  $("#jobTitle").textContent = (JOB_LABEL[job.name] || job.name) + state;
  $("#jobLog").textContent = (job.log || []).join("\n") || "(等待输出...)";
  $("#jobLog").scrollTop = $("#jobLog").scrollHeight;
  if (job.running) {
    jobWasRunning = true;
    jobTimer = setTimeout(loadStaging, 3000);
  } else if (jobWasRunning) {
    jobWasRunning = false;
    if (job.returncode === 0 && job.name === "images") {
      api("/reload", { method: "POST" })
        .then(m => { renderMeta(m); toast("图片索引已更新并重载"); })
        .catch(() => {});
    } else if (job.returncode === 0) {
      toast(JOB_LABEL[job.name] + "完成,请核对 diff");
    } else {
      toast(JOB_LABEL[job.name] + "失败,看日志", true);
    }
  }
}

function renderStaging(d) {
  const box = $("#stgBox");
  const badge = $("#stgBadge");
  if (!d.exists) {
    badge.classList.add("hidden");
    box.innerHTML = `<p class="dim">当前没有 staging。点「完整重建」(全量,约 3 分钟)
      或「快速刷新」(只更新战队/状态/位置)抓一份新数据,过目 diff 后再发布。
      ${d.backup_exists ? "上次发布的备份 players.json.bak 还在。" : ""}</p>`;
    return;
  }
  if (d.invalid) {
    box.innerHTML = `<p class="err">staging 文件损坏: ${esc(d.invalid)}</p>`;
    return;
  }
  const c = d.diff.counts;
  const total = c.added + c.removed + c.changed;
  badge.textContent = total;
  badge.classList.remove("hidden");
  const table = (rows, cls) => rows.length ? `
    <table class="p-table">
      <tr><th>ID</th><th>战队</th><th>国籍</th><th>Major</th><th>page</th></tr>
      ${rows.map(p => `<tr class="${cls}"><td><b>${esc(p.nickname)}</b></td>
        <td>${esc(p.team || "自由身")}</td><td>${esc(p.country)}</td>
        <td>${p.majors_count}</td><td class="dim">${esc(p.page)}</td></tr>`).join("")}
    </table>` : `<span class="dim">无</span>`;
  const changed = d.diff.changed.length ? d.diff.changed.map(x => `
    <div class="chg"><b class="chg-who" data-page="${esc(x.page)}">${esc(x.nickname)}</b>
      ${x.changes.map(ch => `<span class="chg-item">${esc(FIELD_LABEL[ch.field] || ch.field)}:
        <s>${esc(JSON.stringify(ch.old) ?? "")}</s> → <b>${esc(JSON.stringify(ch.new) ?? "")}</b></span>`).join("")}
    </div>`).join("") : `<span class="dim">无</span>`;
  box.innerHTML = `
    <div class="stg-summary">
      <span>staging 抓取于 <b>${esc((d.generated_at || "").slice(0, 16).replace("T", " "))}</b>,
        共 <b>${d.count}</b> 人(现库 ${d.current_count} 人,
        ${esc((d.current_generated_at || "").slice(0, 10))})</span>
      <span class="cnt">+${c.added} / -${c.removed} / ~${c.changed}</span>
      <button id="stgPromote" class="mini-btn save-strong">发布(备份并替换)</button>
      <button id="stgDiscard" class="mini-btn del-weak">丢弃 staging</button>
    </div>
    <details class="h-sec" ${c.added && c.added <= 30 ? "open" : ""}>
      <summary><span class="cnt">${c.added}</span> 新增选手</summary>
      <div class="h-body">${table(d.diff.added, "add")}
        ${c.added ? `<p class="dim">发布后记得点「补齐图片」给新选手抓照片。</p>` : ""}</div>
    </details>
    <details class="h-sec" ${c.removed ? "open" : ""}>
      <summary><span class="cnt">${c.removed}</span> 移除选手
        <span class="desc">现库有、staging 没有;大量移除多半是上游页面异常</span></summary>
      <div class="h-body">${table(d.diff.removed, "del")}</div>
    </details>
    <details class="h-sec" ${c.changed && c.changed <= 50 ? "open" : ""}>
      <summary><span class="cnt">${c.changed}</span> 字段变动</summary>
      <div class="h-body">${changed}</div>
    </details>`;
  $("#stgPromote").addEventListener("click", () => promoteStaging(false));
  $("#stgDiscard").addEventListener("click", async () => {
    if (!confirm("丢弃 staging 文件?")) return;
    try { await api("/staging", { method: "DELETE" }); toast("已丢弃"); loadStaging(); }
    catch (e) { toast("丢弃失败: " + e.message, true); }
  });
  $$("#stgBox .chg-who").forEach(b =>
    b.addEventListener("click", () => gotoPlayerTab(b.dataset.page)));
}

async function promoteStaging(force) {
  if (!force && !confirm("发布 staging 到正式库?旧库会备份为 players.json.bak,发布后立即热重载。")) return;
  try {
    const m = await api("/staging/promote", {
      method: "POST", body: JSON.stringify({ force }),
    });
    renderMeta(m);
    toast(`已发布 ${m.promoted_count} 人并重载`);
    loadStaging();
  } catch (e) {
    if (!force && String(e.message).includes("force")) {
      if (confirm(e.message + "\n\n确认仍要发布?")) promoteStaging(true);
    } else {
      toast("发布失败: " + e.message, true);
    }
  }
}

async function startJob(name) {
  try {
    await api("/jobs/" + name, { method: "POST" });
    toast(JOB_LABEL[name] + " 已启动");
    loadStaging();
  } catch (e) { toast(e.message, true); }
}
$("#jobBuild").addEventListener("click", () =>
  confirm("完整重建约 3 分钟(Liquipedia 限速),写入 staging,不影响线上。继续?") && startJob("build"));
$("#jobRefresh").addEventListener("click", () => startJob("refresh"));
$("#jobImages").addEventListener("click", () => startJob("images"));
$("#stgRefresh").addEventListener("click", loadStaging);

/* ------------------------------------------------------ hltv 审核 */
let hltvCache = null;

async function loadHltv() {
  try {
    hltvCache = await api("/hltv/review");
    renderHltv();
  } catch (e) { toast("审核文件加载失败: " + e.message, true); }
}

function renderHltv() {
  const d = hltvCache;
  const badge = $("#hltvBadge");
  const list = $("#hltvList");
  if (!d.exists) {
    badge.classList.add("hidden");
    list.innerHTML = `<p class="dim">还没有审核文件(${esc(d.path || "")})。
      先在本机跑 collect(需要本地 Chrome,不能从网页触发):</p>
      <pre>.\\.venv\\Scripts\\python -X utf8 scripts\\sync_hltv_roles.py collect --players 选手1 选手2 --with-igl-news</pre>`;
    return;
  }
  if (d.invalid) { list.innerHTML = `<p class="err">审核文件损坏: ${esc(d.invalid)}</p>`; return; }
  badge.textContent = d.pending;
  badge.classList.toggle("hidden", !d.pending);
  const only = $("#hltvOnlyPending").checked;
  const rows = d.players.filter(r => !only || !r.decision);
  const head = `<p class="dim">采集于 ${esc((d.generated_at || "").slice(0, 16).replace("T", " "))}
    · 共 ${d.players.length} 条 · 未决 ${d.pending}
    ${d.stopped_early ? `<span class="err">(上次采集被 403 熔断,清单不全)</span>` : ""}</p>`;
  if (!rows.length) { list.innerHTML = head + `<p class="dim">没有${only ? "未决" : ""}条目。</p>`; return; }
  list.innerHTML = head + rows.map(r => {
    const sug = r.suggestion || {};
    const prof = r.profile || {};
    const evid = (r.igl_evidence || []).slice(0, 5);
    return `
    <div class="hltv-card ${r.decision ? "decided" : ""}">
      <div class="hl-main">
        <div class="hl-who">
          <b class="chg-who" data-page="${esc(r.local_page)}">${esc(r.nickname)}</b>
          <span class="dim">${esc(r.real_name || "")} · ${esc(r.team || "自由身")}
            · ${esc(r.status || "?")}</span><br>
          <span class="dim">本地标签: ${esc((r.local_roles || []).join(", ") || "无")}
            → 当前推断 <b>${esc(r.current_inference || "?")}</b></span>
        </div>
        <div class="hl-evid">
          ${r.match ? `<a href="${esc(r.match.url)}" target="_blank" rel="noopener">HLTV 主页 ↗</a>
            <span class="dim">(${esc(r.match_reason || "")})</span>` : `<span class="err">未匹配到 HLTV</span>`}
          ${prof.recent_maps != null ? `<span>近3月 ${prof.recent_maps} 图</span>` : ""}
          ${prof.sniping_score != null ? `<span>Sniping ${prof.sniping_score}/100</span>` : ""}
          ${sug.suggested_role
            ? `<span class="hl-sug ${esc(sug.confidence)}">建议 ${esc(sug.suggested_role)}
               [${esc(sug.confidence)}]</span>`
            : `<span class="dim">无自动建议</span>`}
          ${sug.reason ? `<div class="dim">${esc(sug.reason)}</div>` : ""}
          ${evid.length ? `<div class="hl-links">IGL 证据:
            ${evid.map(x => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.kind || "链接")}</a>`).join(" · ")}</div>` : ""}
          ${r.error ? `<div class="err">${esc(r.error)}</div>` : ""}
        </div>
      </div>
      <div class="hl-decide">
        <select class="hl-role">
          ${["", "IGL", "AWPer", "Rifler", "Coach"].map(v =>
            `<option value="${v}" ${(r.decision || "") === v ? "selected" : ""}>${v || "(未决)"}</option>`).join("")}
        </select>
        <select class="hl-field">
          ${["game_role", "played_role"].map(v =>
            `<option ${(r.decision_field || "game_role") === v ? "selected" : ""}>${v}</option>`).join("")}
        </select>
        <button class="mini-btn hl-save" data-page="${esc(r.local_page)}">保存</button>
      </div>
    </div>`;
  }).join("");
  $$("#hltvList .chg-who").forEach(b =>
    b.addEventListener("click", () => gotoPlayerTab(b.dataset.page)));
  $$("#hltvList .hl-save").forEach(b => b.addEventListener("click", async () => {
    const card = b.closest(".hltv-card");
    const decision = card.querySelector(".hl-role").value || null;
    const field = card.querySelector(".hl-field").value;
    try {
      await api(`/hltv/review/${encodeURIComponent(b.dataset.page)}/decision`, {
        method: "PUT",
        body: JSON.stringify({ decision, decision_field: field }),
      });
      const row = hltvCache.players.find(x => x.local_page === b.dataset.page);
      if (row) { row.decision = decision; row.decision_field = field; }
      hltvCache.pending = hltvCache.players.filter(x => !x.decision).length;
      toast(`${b.dataset.page}: ${decision || "已清除决定"}`);
      renderHltv();
    } catch (e) { toast("保存失败: " + e.message, true); }
  }));
}

async function hltvApply(write) {
  if (write && !confirm("把所有已填 decision 的条目写入 player_overrides.json?\n默认保护已有人工角色,除非勾选了「替换已有 override」。")) return;
  try {
    const d = await api("/hltv/apply", {
      method: "POST",
      body: JSON.stringify({ write, replace_existing: $("#hltvReplace").checked }),
    });
    const out = $("#hltvApplyOut");
    out.classList.remove("hidden");
    out.textContent = (write ? `已写入 ${d.changed} 项\n` : `预览: ${d.changed} 项可更新(未写文件)\n`)
      + (d.messages.join("\n") || "(没有已填 decision 的条目)");
    if (d.reload) { renderMeta(d.reload); toast("overrides 已更新并热重载"); }
  } catch (e) { toast("apply 失败: " + e.message, true); }
}
$("#hltvPreview").addEventListener("click", () => hltvApply(false));
$("#hltvWrite").addEventListener("click", () => hltvApply(true));
$("#hltvRefresh").addEventListener("click", loadHltv);
$("#hltvOnlyPending").addEventListener("change", renderHltv);

/* ----------------------------------------------------------- init */
if (TOKEN) enter(); else showLogin();
