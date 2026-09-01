# -*- coding: utf-8 -*-
"""管理页面:反馈收件箱 / 选手 override 编辑 / 数据体检 / 热重载。

安全模型:未配置 ADMIN_TOKEN 时 /admin 与 /api/admin/* 一律 404,
线上默认关闭;配置后所有接口要求 X-Admin-Token 精确匹配。

写盘一律落在 data/manual/(人工层:override / 人工新增选手 / 上传的
照片),从不改动生成物 players.json,因此与 scraper 重跑完全兼容;改完调
/api/admin/reload 原地重载 PlayerDB 生效,不需要重启进程。

反馈处理状态存放在 feedback.jsonl 旁边的 *.state.json,按行内容哈希
定位条目,原始 JSONL 永远只追加、不改写。
"""
import base64
import binascii
import hashlib
import json
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from playerdb.paths import ROOT as REPO_ROOT

from . import config
from playerdb import players as players_mod
from .assets import versioned_html
from playerdb.regions import canonical_country, region_of

ROOT = Path(__file__).resolve().parent.parent

# 与 players.py 加载逻辑对应的可覆盖字段;其他字段(国籍/赛区/Major 数)
# 牵连派生数据,暂不开放,防止改出不一致。
EDITABLE_FIELDS = ("team", "status", "game_role", "played_role", "birth_date")
GAME_ROLE_VALUES = {"IGL", "AWPer", "Rifler", "Coach"}
# 上游 status 的全部取值。之前 override 编辑器把它做成自由文本框,填错一个
# 字就静默失效(is_active 只认 "retired"),所以收敛成白名单 + 下拉。
STATUS_VALUES = {"Active", "Inactive", "Retired"}
PLAYED_ROLE_VALUES = {"IGL", "AWPer", "Rifler"}
BIRTH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_raw_cache: dict = {"mtime": None, "by_page": {}}

# ------------------------------------------------------- staging & diff
# staging 工作流:scraper --out 写到 players.staging.json,管理页 diff
# 过目后「发布」才替换正式库(旧库备份为 players.json.bak)。
DIFF_FIELDS = ("nickname", "real_name", "country", "team", "status",
               "birth_date", "roles", "majors_count", "in_blast_pool")

# HLTV 角色审核文件(gtptools/sync_hltv_roles.py collect 的输出)
HLTV_REVIEW_PATH = REPO_ROOT / ".cache" / "hltv" / "role_review.json"


def _staging_path() -> Path:
    return players_mod.DATA_PATH.with_name("players.staging.json")


def _backup_path() -> Path:
    return players_mod.DATA_PATH.with_name("players.json.bak")


def _diff_brief(rec: dict) -> dict:
    return {"page": rec.get("page", ""), "nickname": rec.get("nickname", ""),
            "team": rec.get("team", ""), "country": rec.get("country", ""),
            "majors_count": rec.get("majors_count", 0)}


def diff_players(cur: dict, stg: dict) -> dict:
    """比较两份 players.json 文档,产出发布前人工过目的变更清单。"""
    cur_by = {str(r.get("page", "")): r for r in cur.get("players", [])}
    stg_by = {str(r.get("page", "")): r for r in stg.get("players", [])}
    added = sorted((_diff_brief(stg_by[p]) for p in stg_by if p not in cur_by),
                   key=lambda x: x["nickname"].lower())
    removed = sorted((_diff_brief(cur_by[p]) for p in cur_by if p not in stg_by),
                     key=lambda x: x["nickname"].lower())
    changed = []
    for page, new in stg_by.items():
        old = cur_by.get(page)
        if old is None:
            continue
        changes = [{"field": f, "old": old.get(f), "new": new.get(f)}
                   for f in DIFF_FIELDS if old.get(f) != new.get(f)]
        if changes:
            changed.append({"page": page, "nickname": new.get("nickname", ""),
                            "changes": changes})
    changed.sort(key=lambda x: x["nickname"].lower())
    return {"added": added, "removed": removed, "changed": changed,
            "counts": {"added": len(added), "removed": len(removed),
                       "changed": len(changed)}}


def team_igl_conflicts(players) -> list:
    """现役同队 2 个及以上 IGL:多半是上游残留的历史指挥标签
    (交接指挥后 Liquipedia 常忘了摘旧人的 igl)。"""
    by_team: dict[str, list] = {}
    for p in players:
        if p.is_active and p.primary_role == "IGL":
            by_team.setdefault(p.team, []).append(p)
    out = []
    for team in sorted(by_team, key=str.lower):
        group = by_team[team]
        if len(group) >= 2:
            out.extend(group)
    return out


# 判定"这是一套真在打的首发",而不是残缺的历史队史
MIN_ROSTER = 4


def teams_without_igl(players) -> list:
    """现役阵容一个 IGL 都没有:上游漏标指挥的典型症状。
    和 team_igl_conflicts 对称——那个查交接后残留的旧标签(≥2 个指挥),
    这个查压根没人被标成指挥。后者不主动列出来的话,只能靠人工恰好
    认识这队才发现(Magisk@BC.Game 就是这么撞见的)。
    返回整套阵容而不只是"缺的那个人",因为指挥是谁只能人工判断。"""
    by_team: dict[str, list] = {}
    for p in players:
        if p.is_active and p.team:
            by_team.setdefault(p.team, []).append(p)
    out = []
    for team in sorted(by_team, key=str.lower):
        group = by_team[team]
        if len(group) >= MIN_ROSTER and not any(
                p.primary_role == "IGL" for p in group):
            out.extend(group)
    return out


def orphan_overrides(players, overrides: dict) -> list:
    """匹配不到任何选手的 override 条目。override 以 Liquipedia page 名为
    键,上游一旦改页名(Rain -> Rain (Norwegian player)),这条人工结论就
    静默失效——没有报错,只是某个角色某天"自己变回去了"。所以主动列出来。"""
    pages = {str(p.page).casefold() for p in players}
    return [{"key": k, "override": v} for k, v in overrides.items()
            if k.casefold() not in pages]


def _hltv_mod():
    """gtptools/sync_hltv_roles.py 顶层只有标准库,playwright 是懒加载,
    服务端 import 它复用 apply 的保护逻辑是安全的。"""
    from gtptools import sync_hltv_roles
    return sync_hltv_roles


# ---------------------------------------------------------- job runner
# 管理页触发的维护子进程(抓数据/补图片),单飞:同时只允许一个。
JOBS = {
    "build": lambda: [sys.executable, "-X", "utf8", "-u",
                      "-m", "playerdb.scrape.build_db",
                      "--out", str(_staging_path())],
    "refresh": lambda: [sys.executable, "-X", "utf8", "-u",
                        "-m", "playerdb.scrape.build_db",
                        "--refresh-existing", "--out", str(_staging_path())],
    "images": lambda: [sys.executable, "-X", "utf8", "-u",
                       "-m", "playerdb.scrape.fetch_images"],
}
JOB_LOG_MAX = 400
_job_lock = threading.Lock()
_job: dict = {"name": None, "running": False, "started_at": None,
              "finished_at": None, "returncode": None, "log": []}


def _run_job(name: str, cmd: list[str]) -> None:
    try:
        proc = subprocess.Popen(
            cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace")
        with proc.stdout:
            for line in proc.stdout:
                with _job_lock:
                    _job["log"].append(line.rstrip("\n"))
                    if len(_job["log"]) > JOB_LOG_MAX:
                        del _job["log"][:len(_job["log"]) - JOB_LOG_MAX]
        rc = proc.wait()
    except OSError as e:
        with _job_lock:
            _job["log"].append(f"启动失败: {e}")
        rc = -1
    with _job_lock:
        _job["running"] = False
        _job["returncode"] = rc
        _job["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")


def require_admin(admin_token: str = Header(default="", alias="X-Admin-Token")):
    if not config.ADMIN_TOKEN:
        raise HTTPException(404, "Not Found")
    if not secrets.compare_digest(admin_token, config.ADMIN_TOKEN):
        raise HTTPException(401, "管理口令不正确")


# ------------------------------------------------------------- file helpers
def _raw_players() -> dict:
    """players.json 原始记录(按 page 索引),按 mtime 缓存。"""
    path = players_mod.DATA_PATH
    mtime = path.stat().st_mtime
    if _raw_cache["mtime"] != mtime:
        raw = json.loads(path.read_text(encoding="utf-8"))
        _raw_cache["by_page"] = {str(r.get("page", "")): r for r in raw["players"]}
        _raw_cache["mtime"] = mtime
    return _raw_cache["by_page"]


def _atomic_write_json(path: Path, data) -> None:
    # tmp 必须和目标同目录:rename 跨设备会失败,而人工层是独立挂载的卷。
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        raise HTTPException(500, f"写入 {path.name} 失败(只读部署?): {e}")


def _load_overrides() -> dict:
    p = players_mod.overrides_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _load_manual() -> dict:
    """人工新增选手表,保留 note 字段原样写回。"""
    data = players_mod._read_json(players_mod.MANUAL_PLAYERS_PATH)
    if not isinstance(data, dict):
        data = {"players": data or []}
    data.setdefault("players", [])
    return data


def _manual_index(data: dict, page: str) -> int:
    for i, r in enumerate(data["players"]):
        if str(r.get("page", "")).casefold() == page.casefold():
            return i
    return -1


def _override_key(overrides: dict, page: str) -> str:
    """复用已有条目的原始大小写键,避免同一选手出现两个条目。"""
    for k in overrides:
        if k.casefold() == page.casefold():
            return k
    return page


def _state_path() -> Path:
    fp = config.FEEDBACK_PATH
    return fp.with_name(fp.stem + ".state.json")


def _load_feedback_state() -> dict:
    p = _state_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def _feedback_entries() -> list[dict]:
    path = config.FEEDBACK_PATH
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        # 内容哈希做 id:JSONL 只追加,同内容重复行共享一个处理状态
        fid = hashlib.sha1(line.encode("utf-8")).hexdigest()[:12]
        out.append({
            "id": fid,
            "ts": rec.get("ts", ""),
            "ip": rec.get("ip", ""),
            "page": rec.get("page", ""),
            "message": rec.get("message", ""),
            "context": rec.get("context", ""),
        })
    return out


# ------------------------------------------------------------------ bodies
class OverrideBody(BaseModel):
    fields: dict
    reason: str


class FeedbackStateBody(BaseModel):
    resolved: bool
    note: str = ""


class PromoteBody(BaseModel):
    force: bool = False


class DecisionBody(BaseModel):
    decision: str | None = None          # None/空 = 清除决定
    decision_field: str = "game_role"


class HltvApplyBody(BaseModel):
    write: bool = False
    replace_existing: bool = False


class ManualPlayerBody(BaseModel):
    """人工新增选手。page 是主键(和 Liquipedia 页名同一个命名空间),
    新增后由 players.py 在加载时合并,爬虫重建不会冲掉。"""
    page: str = ""
    nickname: str
    real_name: str = ""
    country: str = ""
    birth_date: str = ""
    team: str = ""
    status: str = "Active"
    game_role: str = ""
    roles: list[str] = []
    majors_count: int = 0
    in_blast_pool: bool = False
    reason: str


class PhotoBody(BaseModel):
    """照片走 base64 而不是 multipart:multipart 要额外装 python-multipart,
    为了一年传几张彩蛋头像给生产镜像加依赖不划算。"""
    filename: str = ""
    data: str                            # 纯 base64 或 data:image/...;base64,


# 头像上传:运行时镜像里没有 Pillow(只在 requirements-maintenance.txt),
# 所以只认魔数和体积,不解码、不缩放。结算卡按 240px 渲染、2x 屏 480px,
# 建议仍然上传 600px 源图。
PHOTO_MAX_BYTES = 2 * 1024 * 1024
PHOTO_MAGIC = ((b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png"))
UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _photo_ext(blob: bytes) -> str:
    for magic, ext in PHOTO_MAGIC:
        if blob.startswith(magic):
            return ext
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    raise HTTPException(400, "只支持 JPEG / PNG / WebP 图片")


def _decode_photo(data: str) -> bytes:
    raw = data.split(",", 1)[-1] if data.startswith("data:") else data
    try:
        blob = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(400, "图片不是合法的 base64")
    if not blob:
        raise HTTPException(400, "图片为空")
    if len(blob) > PHOTO_MAX_BYTES:
        raise HTTPException(400,
                            f"图片超过 {PHOTO_MAX_BYTES // 1024 // 1024}MB")
    return blob


def _manual_record(body: "ManualPlayerBody", page: str) -> dict:
    """组装成和 players.json 同构的记录,让下游(Player/前端)无需区分来源。"""
    country = body.country.strip()
    if country:
        canonical = canonical_country(country)
        if canonical is None:
            raise HTTPException(
                400, f"未知国籍 {country!r};必须用国籍表里的英文写法"
                     "(表单里改用下拉选择)")
        country = canonical
    if body.status and body.status not in STATUS_VALUES:
        raise HTTPException(400, f"status 只能是 {sorted(STATUS_VALUES)}")
    roles = [r.strip().lower() for r in body.roles if r.strip()]
    unknown = [r for r in roles if r not in players_mod.ROLE_LABEL]
    if unknown:
        raise HTTPException(400, f"未知 roles: {unknown}")
    if body.birth_date and not BIRTH_RE.match(body.birth_date):
        raise HTTPException(400, "birth_date 格式须为 YYYY-MM-DD")
    if body.game_role and body.game_role not in GAME_ROLE_VALUES:
        raise HTTPException(400, f"game_role 只能是 {sorted(GAME_ROLE_VALUES)}")
    return {
        "page": page,
        "nickname": body.nickname.strip(),
        "real_name": body.real_name.strip(),
        "country": country,
        "region": region_of(country),
        "birth_date": body.birth_date.strip(),
        "team": body.team.strip(),
        "source_team": body.team.strip(),
        "current_team_history": [],
        "team_resolution": "manual",
        "status": body.status or "Active",
        "roles": roles,
        "game_role": body.game_role,
        "majors_count": max(0, body.majors_count),
        "first_major_year": None,
        "last_major_year": None,
        "majors": [],
        "in_blast_pool": body.in_blast_pool,
        "manual_reason": body.reason.strip(),
    }


def _admin_brief(p, has_override: bool) -> dict:
    return {
        "page": p.page,
        "nickname": p.nickname,
        "real_name": p.real_name or "",
        "country": p.country or "",
        "team": p.team or "",
        "status": p.status or "",
        "birth_date": p.birth_date or "",
        "age": p.age(),
        "role": p.primary_role,
        "majors_count": p.majors_count or 0,
        "photo": p.photo,
        "game_ready": p.is_game_ready,
        "has_override": has_override,
        "manual": p.is_manual,
    }


def build_admin_router(db) -> APIRouter:
    router = APIRouter()
    guarded = APIRouter(prefix="/api/admin",
                        dependencies=[Depends(require_admin)])

    @router.get("/admin")
    def admin_page():
        if not config.ADMIN_TOKEN:
            raise HTTPException(404, "Not Found")
        return versioned_html(ROOT / "static" / "admin.html")

    @guarded.get("/ping")
    def ping():
        return {
            "ok": True,
            "db_generated_at": db.generated_at,
            "player_count": len(db.players),
            "answer_player_count": len(db.answer_players),
        }

    # ------------------------------------------------------------ feedback
    @guarded.get("/feedback")
    def feedback_list():
        state = _load_feedback_state()
        entries = _feedback_entries()
        entries.reverse()               # 新的在前
        for e in entries:
            st = state.get(e["id"], {})
            e["resolved"] = bool(st.get("resolved"))
            e["note"] = st.get("note", "")
            p = db.by_page.get(e["page"]) or db.lookup(e["page"])
            e["player"] = _admin_brief(p, False) if p else None
        return {"entries": entries,
                "open_count": sum(1 for e in entries if not e["resolved"])}

    @guarded.post("/feedback/{fid}/state")
    def feedback_state(fid: str, body: FeedbackStateBody):
        if not any(e["id"] == fid for e in _feedback_entries()):
            raise HTTPException(404, "反馈条目不存在")
        state = _load_feedback_state()
        state[fid] = {
            "resolved": body.resolved,
            "note": body.note.strip()[:300],
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        _atomic_write_json(_state_path(), state)
        return {"ok": True, "id": fid, **state[fid]}

    # ------------------------------------------------------------- players
    @guarded.get("/players")
    def search_players(q: str = "", limit: int = 30, offset: int = 0):
        """q 为空时返回整库(按名气排序),让「选手编辑」一进去就有列表可翻,
        不必先想出一个搜索词;offset 给前端翻页用,六百多人一次铺完没法看。"""
        q = q.strip()
        overrides = {k.casefold() for k in _load_overrides()}
        if q:
            key = players_mod._fold(q)
            hits = [p for p in db.players
                    if key in players_mod._fold(p.nickname)
                    or key in players_mod._fold(p.page)
                    or key in players_mod._fold(p.real_name or "")]
        else:
            hits = list(db.players)
        hits.sort(key=db._fame, reverse=True)
        total = len(hits)
        offset = max(0, min(offset, total))
        hits = hits[offset:]
        if limit > 0:
            hits = hits[:limit]
        return {"total": total, "offset": offset, "players": [
            _admin_brief(p, p.page.casefold() in overrides) for p in hits]}

    @guarded.get("/players/{page}")
    def player_detail(page: str):
        p = db.by_page.get(page)
        if p is None:
            raise HTTPException(404, "选手不存在")
        # 人工新增的选手不在 players.json 里,「爬取值」一栏改看人工原始记录。
        raw = _raw_players().get(p.page, {})
        if not raw and p.is_manual:
            data = _load_manual()
            i = _manual_index(data, p.page)
            raw = data["players"][i] if i >= 0 else {}
        overrides = _load_overrides()
        entry = overrides.get(_override_key(overrides, p.page), None)
        fb = [e for e in _feedback_entries()
              if e["page"].casefold() == p.page.casefold()]
        fb.reverse()
        state = _load_feedback_state()
        for e in fb:
            e["resolved"] = bool(state.get(e["id"], {}).get("resolved"))
        return {
            "effective": {**_admin_brief(p, entry is not None),
                          "region": p.region,
                          "roles": p.roles,
                          "game_role": p.game_role or "",
                          "flag": p.flag,
                          "team_logo": p.team_logo,
                          "manual_photo": p.page in db.manual_photo_map},
            "scraped": {k: raw.get(k) for k in
                        ("team", "status", "roles", "birth_date", "country",
                         "majors_count", "in_blast_pool", "manual_reason")},
            "override": entry,
            "feedback": fb,
        }

    @guarded.put("/players/{page}/override")
    def put_override(page: str, body: OverrideBody):
        p = db.by_page.get(page)
        if p is None:
            raise HTTPException(404, "选手不存在")
        reason = body.reason.strip()
        if not reason:
            raise HTTPException(400, "必须填写 reason(修改依据)")
        if not body.fields:
            raise HTTPException(400, "没有要覆盖的字段")
        entry: dict = {}
        for k, v in body.fields.items():
            if k not in EDITABLE_FIELDS:
                raise HTTPException(400, f"不支持覆盖字段: {k}")
            if not isinstance(v, str):
                raise HTTPException(400, f"字段 {k} 必须是字符串")
            v = v.strip()
            if k == "game_role" and v not in GAME_ROLE_VALUES:
                raise HTTPException(400, f"game_role 只能是 {sorted(GAME_ROLE_VALUES)}")
            if k == "played_role" and v not in PLAYED_ROLE_VALUES:
                raise HTTPException(400, f"played_role 只能是 {sorted(PLAYED_ROLE_VALUES)}")
            if k == "birth_date" and not BIRTH_RE.match(v):
                raise HTTPException(400, "birth_date 格式须为 YYYY-MM-DD")
            entry[k] = v
        entry["reason"] = reason
        overrides = _load_overrides()
        overrides[_override_key(overrides, p.page)] = entry
        _atomic_write_json(players_mod.OVERRIDES_PATH, overrides)
        return {"ok": True, "page": p.page, "override": entry}

    @guarded.delete("/players/{page}/override")
    def delete_override(page: str):
        overrides = _load_overrides()
        key = _override_key(overrides, page)
        if key not in overrides:
            raise HTTPException(404, "该选手没有 override")
        overrides.pop(key)
        _atomic_write_json(players_mod.OVERRIDES_PATH, overrides)
        return {"ok": True, "page": page}

    # ------------------------------------------------- 人工新增选手
    # 彩蛋选手/上游查不到的人。写 data/manual/players_manual.json,加载时
    # 合并——直接塞进 players.json 的话会被下一次整库重建冲掉(MachineWJQ
    # 就这么丢过一次,见 52f0b5f)。
    @guarded.get("/manual")
    def list_manual():
        pages = {str(r.get("page", "")).casefold()
                 for r in _load_manual()["players"]}
        overrides = {k.casefold() for k in _load_overrides()}
        return {"players": [
            _admin_brief(p, p.page.casefold() in overrides)
            for p in db.players if p.page.casefold() in pages]}

    @guarded.post("/manual")
    def create_manual(body: ManualPlayerBody):
        page = (body.page or body.nickname).strip()
        if not page or not body.nickname.strip():
            raise HTTPException(400, "必须填写昵称")
        if not body.reason.strip():
            raise HTTPException(400, "必须填写 reason(新增依据)")
        if any(p.page.casefold() == page.casefold() for p in db.players):
            raise HTTPException(409, f"{page} 已存在,请直接编辑或换一个 page")
        data = _load_manual()
        if _manual_index(data, page) >= 0:
            raise HTTPException(409, f"{page} 已在人工新增表里")
        rec = _manual_record(body, page)
        data["players"].append(rec)
        _atomic_write_json(players_mod.MANUAL_PLAYERS_PATH, data)
        return {"ok": True, "page": page, "record": rec}

    @guarded.put("/manual/{page}")
    def update_manual(page: str, body: ManualPlayerBody):
        if not body.reason.strip():
            raise HTTPException(400, "必须填写 reason(修改依据)")
        data = _load_manual()
        i = _manual_index(data, page)
        if i < 0:
            raise HTTPException(404, f"{page} 不是人工新增的选手")
        rec = _manual_record(body, data["players"][i]["page"])
        data["players"][i] = rec
        _atomic_write_json(players_mod.MANUAL_PLAYERS_PATH, data)
        return {"ok": True, "page": rec["page"], "record": rec}

    @guarded.delete("/manual/{page}")
    def delete_manual(page: str):
        data = _load_manual()
        i = _manual_index(data, page)
        if i < 0:
            raise HTTPException(404, f"{page} 不是人工新增的选手")
        real_page = data["players"].pop(i)["page"]
        _atomic_write_json(players_mod.MANUAL_PLAYERS_PATH, data)
        # 顺带清掉这个人的人工照片,免得留下引用不到的孤儿文件
        imgs = players_mod._read_json(players_mod.MANUAL_IMAGES_PATH)
        rel = imgs.get("players", {}).pop(real_page, None)
        if rel:
            _atomic_write_json(players_mod.MANUAL_IMAGES_PATH, imgs)
            (players_mod.MANUAL_IMG_DIR / rel).unlink(missing_ok=True)
        return {"ok": True, "page": real_page}

    @guarded.put("/players/{page}/photo")
    def upload_photo(page: str, body: PhotoBody):
        """人工照片对所有选手都生效(不止新增的),优先级高于爬取的图。"""
        p = db.by_page.get(page)
        if p is None:
            raise HTTPException(404, "选手不存在")
        blob = _decode_photo(body.data)
        ext = _photo_ext(blob)
        rel = f"players/{UNSAFE_NAME_RE.sub('_', p.page)}.{ext}"
        dest = players_mod.MANUAL_IMG_DIR / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".tmp")
            tmp.write_bytes(blob)
            tmp.replace(dest)
        except OSError as e:
            raise HTTPException(500, f"写入照片失败(只读部署?): {e}")
        imgs = players_mod._read_json(players_mod.MANUAL_IMAGES_PATH)
        imgs.setdefault("players", {})
        old = imgs["players"].get(p.page)
        imgs["players"][p.page] = rel
        _atomic_write_json(players_mod.MANUAL_IMAGES_PATH, imgs)
        if old and old != rel:            # 换了扩展名,旧文件不再被引用
            (players_mod.MANUAL_IMG_DIR / old).unlink(missing_ok=True)
        return {"ok": True, "page": p.page, "rel": rel, "bytes": len(blob)}

    @guarded.delete("/players/{page}/photo")
    def delete_photo(page: str):
        imgs = players_mod._read_json(players_mod.MANUAL_IMAGES_PATH)
        rel = imgs.get("players", {}).pop(page, None)
        if not rel:
            raise HTTPException(404, "该选手没有人工照片")
        _atomic_write_json(players_mod.MANUAL_IMAGES_PATH, imgs)
        (players_mod.MANUAL_IMG_DIR / rel).unlink(missing_ok=True)
        return {"ok": True, "page": page}

    # -------------------------------------------------------------- reload
    def _swap_db() -> dict:
        fresh = players_mod.PlayerDB(players_mod.DATA_PATH)
        # 原地替换:rooms/games 等持有的 db 引用继续有效,
        # 进行中的对局仍握着旧 Player 对象,不受影响。
        db.__dict__.clear()
        db.__dict__.update(fresh.__dict__)
        return {"ok": True,
                "db_generated_at": db.generated_at,
                "player_count": len(db.players),
                "answer_player_count": len(db.answer_players)}

    @guarded.post("/reload")
    def reload_db():
        return _swap_db()

    # ------------------------------------------------------- staging diff
    @guarded.get("/staging")
    def staging_status():
        with _job_lock:
            job = {k: (list(v) if isinstance(v, list) else v)
                   for k, v in _job.items()}
        job["log"] = job["log"][-80:]
        sp = _staging_path()
        if not sp.exists():
            return {"exists": False, "job": job,
                    "backup_exists": _backup_path().exists()}
        try:
            stg = json.loads(sp.read_text(encoding="utf-8"))
            cur = json.loads(
                players_mod.DATA_PATH.read_text(encoding="utf-8"))
        except ValueError as e:
            return {"exists": True, "invalid": str(e), "job": job,
                    "backup_exists": _backup_path().exists()}
        return {"exists": True,
                "generated_at": stg.get("generated_at", ""),
                "count": stg.get("count", len(stg.get("players", []))),
                "current_generated_at": cur.get("generated_at", ""),
                "current_count": cur.get("count", len(cur.get("players", []))),
                "diff": diff_players(cur, stg),
                "job": job,
                "backup_exists": _backup_path().exists()}

    @guarded.post("/staging/promote")
    def staging_promote(body: PromoteBody):
        sp = _staging_path()
        if not sp.exists():
            raise HTTPException(404, "没有 staging 文件,先跑一次抓取")
        try:
            stg = json.loads(sp.read_text(encoding="utf-8"))
        except ValueError as e:
            raise HTTPException(400, f"staging 文件损坏: {e}")
        players = stg.get("players")
        if not isinstance(players, list) or not players:
            raise HTTPException(400, "staging 里没有选手记录,拒绝发布")
        cur_path = players_mod.DATA_PATH
        cur_count = len(json.loads(
            cur_path.read_text(encoding="utf-8")).get("players", []))
        # 上游页面被清空/解析失败时数量会骤降,没有 force 不允许发布
        if len(players) < cur_count * 0.8 and not body.force:
            raise HTTPException(
                409, f"staging 只有 {len(players)} 人,比现库 {cur_count} 人"
                     f"少 20% 以上;确认无误请带 force 重发")
        try:
            _backup_path().write_bytes(cur_path.read_bytes())
            sp.replace(cur_path)
        except OSError as e:
            raise HTTPException(500, f"发布失败(只读部署?): {e}")
        meta = _swap_db()
        return {**meta, "promoted_count": len(players),
                "backup": _backup_path().name}

    @guarded.delete("/staging")
    def staging_discard():
        sp = _staging_path()
        if not sp.exists():
            raise HTTPException(404, "没有 staging 文件")
        try:
            sp.unlink()
        except OSError as e:
            raise HTTPException(500, f"删除失败: {e}")
        return {"ok": True}

    # ---------------------------------------------------------------- jobs
    @guarded.get("/jobs")
    def job_status():
        with _job_lock:
            job = {k: (list(v) if isinstance(v, list) else v)
                   for k, v in _job.items()}
        return job

    @guarded.post("/jobs/{name}")
    def job_start(name: str):
        cmd_factory = JOBS.get(name)
        if cmd_factory is None:
            raise HTTPException(404, f"未知任务: {name}")
        with _job_lock:
            if _job["running"]:
                raise HTTPException(409, f"任务 {_job['name']} 还在跑")
            _job.update(name=name, running=True, returncode=None,
                        finished_at=None, log=[],
                        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        threading.Thread(target=_run_job, args=(name, cmd_factory()),
                         daemon=True).start()
        return {"ok": True, "name": name}

    # ------------------------------------------------------- hltv review
    @guarded.get("/hltv/review")
    def hltv_review():
        if not HLTV_REVIEW_PATH.exists():
            return {"exists": False, "path": str(HLTV_REVIEW_PATH)}
        try:
            review = json.loads(HLTV_REVIEW_PATH.read_text(encoding="utf-8"))
        except ValueError as e:
            return {"exists": True, "invalid": str(e)}
        rows = review.get("players") or []
        return {"exists": True,
                "generated_at": review.get("generated_at", ""),
                "stopped_early": bool(review.get("stopped_early")),
                "pending": sum(1 for r in rows if not r.get("decision")),
                "players": rows}

    @guarded.put("/hltv/review/{page}/decision")
    def hltv_decision(page: str, body: DecisionBody):
        if not HLTV_REVIEW_PATH.exists():
            raise HTTPException(404, "没有审核文件,先在本地跑 collect")
        decision = (body.decision or "").strip() or None
        m = _hltv_mod()
        if decision is not None and decision not in m.ROLE_VALUES:
            raise HTTPException(400, f"decision 只能是 {sorted(m.ROLE_VALUES)} 或留空")
        if body.decision_field not in ("game_role", "played_role"):
            raise HTTPException(400, "decision_field 只能是 game_role / played_role")
        review = json.loads(HLTV_REVIEW_PATH.read_text(encoding="utf-8"))
        row = next((r for r in review.get("players", [])
                    if r.get("local_page") == page), None)
        if row is None:
            raise HTTPException(404, f"审核文件里没有 {page}")
        row["decision"] = decision
        row["decision_field"] = body.decision_field
        _atomic_write_json(HLTV_REVIEW_PATH, review)
        return {"ok": True, "page": page, "decision": decision,
                "decision_field": body.decision_field}

    @guarded.post("/hltv/apply")
    def hltv_apply(body: HltvApplyBody):
        if not HLTV_REVIEW_PATH.exists():
            raise HTTPException(404, "没有审核文件,先在本地跑 collect")
        m = _hltv_mod()
        try:
            changed, messages = m.apply_review(
                HLTV_REVIEW_PATH, players_mod.OVERRIDES_PATH,
                write=body.write, replace_existing=body.replace_existing)
        except (ValueError, OSError, json.JSONDecodeError) as e:
            raise HTTPException(400, f"apply 失败: {e}")
        out = {"changed": changed, "messages": messages, "written": body.write}
        if body.write and changed:
            out["reload"] = _swap_db()
        return out

    # -------------------------------------------------------------- health
    @guarded.get("/health")
    def health():
        cats = {"missing_birth_date": [], "missing_role": [],
                "missing_photo": [], "missing_country": [],
                "age_anomaly": [], "not_game_ready": [],
                "team_igl_conflict": [], "team_no_igl": [],
                "orphan_override": []}
        for p in db.players:
            b = None            # 懒构建,多数选手一项不缺
            def brief():
                nonlocal b
                if b is None:
                    b = _admin_brief(p, False)
                return b
            if not p.birth_date:
                cats["missing_birth_date"].append(brief())
            if p.primary_role == "?":
                cats["missing_role"].append(brief())
            if not p.photo:
                cats["missing_photo"].append(brief())
            if not p.country:
                cats["missing_country"].append(brief())
            age = p.age()
            if age is not None and not (14 <= age <= 48):
                cats["age_anomaly"].append(brief())
            if not p.is_game_ready:
                cats["not_game_ready"].append(brief())
        cats["team_igl_conflict"] = [
            _admin_brief(p, False) for p in team_igl_conflicts(db.players)]
        cats["team_no_igl"] = [
            _admin_brief(p, False) for p in teams_without_igl(db.players)]
        cats["orphan_override"] = orphan_overrides(db.players, _load_overrides())
        return {"categories": cats,
                "counts": {k: len(v) for k, v in cats.items()},
                "player_count": len(db.players)}

    router.include_router(guarded)
    return router
