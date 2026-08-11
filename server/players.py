# -*- coding: utf-8 -*-
"""Player database loading, indexing and pool filtering."""
import hashlib
import json
import unicodedata
from datetime import date
from pathlib import Path

from .major_results import apply_major_results, load_major_results
from .rankings import TeamRanking, normalize_team_name


def _fold(s: str) -> str:
    """小写 + 去变音符号(Kovač -> kovac),让本名匹配不挑输入法。"""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c)).lower()

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "players.json"
IMAGES_PATH = Path(__file__).resolve().parent.parent / "data" / "images.json"
IMG_DIR = Path(__file__).resolve().parent.parent / "data" / "img"

# 人工层:管理页唯一会写盘的地方,和爬虫生成物(players.json/images.json/img)
# 分成两个权威源——生成物由本地爬虫产出、随镜像发布;人工层挂可写卷,线上
# 改完再拉回仓库。目录必须整个可写:_atomic_write_json 用同目录 tmp+rename。
MANUAL_DIR = Path(__file__).resolve().parent.parent / "data" / "manual"
OVERRIDES_PATH = MANUAL_DIR / "player_overrides.json"
MANUAL_PLAYERS_PATH = MANUAL_DIR / "players_manual.json"
MANUAL_IMAGES_PATH = MANUAL_DIR / "images_manual.json"
MANUAL_IMG_DIR = MANUAL_DIR / "img"
# 迁进 data/manual/ 之前的老位置。仍然认它:旧检出/旧卷上找不到新文件时
# 静默当成"零条人工修正"会把上百条人工结论一次性作废,代价太大。
LEGACY_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "player_overrides.json"


def overrides_path() -> Path:
    if not OVERRIDES_PATH.exists() and LEGACY_OVERRIDES_PATH.exists():
        return LEGACY_OVERRIDES_PATH
    return OVERRIDES_PATH
HLTV_MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "hltv_player_map.json"
TOP20_PATH = Path(__file__).resolve().parent.parent / "data" / "hltv_top20.json"

ROLE_LABEL = {
    "igl": "IGL",
    "awp": "AWPer", "awper": "AWPer",
    "rifle": "Rifler", "rifler": "Rifler", "lurker": "Rifler",
    "lurk": "Rifler", "entry": "Rifler", "entryfragger": "Rifler",
    "support": "Rifler",
    "coach": "Coach", "head coach": "Coach",
    "analyst": "Analyst", "broadcast analyst": "Analyst",
}
ANSWER_ROLES = {"IGL", "AWPer", "Rifler", "Coach"}
HEAD_COACH_ROLES = {"coach", "head coach"}
STAFF_ROLES = {
    *HEAD_COACH_ROLES,
    "inactive coach",
    "assistant coach",
    "manager",
    "analyst",
    "broadcast analyst",
    "caster",
    "streamer",
    "content creator",
    "observer",
    "host",
}

REGIONS = ["Europe", "CIS", "North America", "South America", "Asia",
           "Oceania", "Middle East & Africa", "Other"]

DIFFICULTIES = ("easy", "medium", "hard")

# 保留上游原始国籍值用于数据追踪，对外按中国大陆版本显示。
CHINA_COUNTRY_LABELS = {
    "China": "中国",
    "Hong Kong": "中国香港",
    "Macau": "中国澳门",
    "Macao": "中国澳门",
    "Taiwan": "中国台湾",
    "Chinese Taipei": "中国台湾",
}


# 图片 URL 的内容版本号。哈希按 (大小, mtime) 缓存:重新部署/重抓时文件
# 时间戳常常变而内容没变,那时只是重算一次哈希,URL 保持不变,浏览器缓存
# 不会被无谓作废;内容真变了哈希才变,URL 随之变化,新图立刻生效。
# 缓存是模块级的,管理页热重载不会重新读盘。
_IMG_VERSIONS: dict[tuple[str, int, int], str] = {}


def _img_version(path: Path) -> str:
    try:
        st = path.stat()
    except OSError:
        return ""
    key = (str(path), st.st_size, st.st_mtime_ns)
    version = _IMG_VERSIONS.get(key)
    if version is None:
        try:
            digest = hashlib.blake2b(path.read_bytes(), digest_size=5)
        except OSError:
            return ""
        version = digest.hexdigest()
        _IMG_VERSIONS[key] = version
    return version


def _img(rel: str | None, base: Path = IMG_DIR, prefix: str = "/img") -> str | None:
    """rel 相对 base;人工层照片存在另一个目录、走另一个挂载点(/img-manual),
    除此之外和生成物照片一样带内容版本号。"""
    if not rel:
        return None
    version = _img_version(base / rel)
    return f"{prefix}/{rel}?v={version}" if version else f"{prefix}/{rel}"


def _manual_img(rel: str | None) -> str | None:
    return _img(rel, MANUAL_IMG_DIR, "/img-manual")


def _read_json(path: Path, default=None):
    """人工层文件缺失/为空时按默认值处理:全新部署时 data/manual 只是个空卷。"""
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {} if default is None else default


def manual_records() -> list[dict]:
    """人工新增的选手(彩蛋/上游查不到的人)。爬虫产物 players.json 会被
    整库重建覆盖——MachineWJQ 就这么丢过一次——所以这些记录单独存放,
    在这里合并进来,重建多少次都不会掉。"""
    data = _read_json(MANUAL_PLAYERS_PATH)
    recs = data.get("players", []) if isinstance(data, dict) else data
    return [r for r in recs if isinstance(r, dict) and r.get("page")]


def _age(birth_date: str, today: date) -> int | None:
    if not birth_date:
        return None
    try:
        y, m, d = (int(x) for x in birth_date.split("-")[:3])
        return today.year - y - ((today.month, today.day) < (m, d))
    except (ValueError, TypeError):
        return None


class Player:
    _FIELDS = ("page", "nickname", "real_name", "country", "region",
               "birth_date", "team", "status", "roles", "majors_count",
               "first_major_year", "last_major_year", "majors", "in_blast_pool",
               "game_role", "team_resolution")
    __slots__ = _FIELDS + ("photo", "team_logo", "flag", "majors_won",
                           "hltv_url", "is_manual")

    def __init__(self, rec: dict, is_manual: bool = False):
        for k in self._FIELDS:
            setattr(self, k, rec.get(k))
        self.roles = self.roles or []
        self.is_manual = is_manual
        self.photo = self.team_logo = self.flag = self.hltv_url = None
        self.majors_won = sum(1 for m in (self.majors or [])
                              if m.get("placement") == "1")

    @property
    def primary_role(self) -> str:
        if self.game_role in ANSWER_ROLES:
            return self.game_role
        # 当前明确是教练时保留 Coach；其余按 IGL、AWP、步枪优先级归一化。
        if self.is_head_coach:
            return "Coach"
        if "igl" in self.roles:
            return "IGL"
        # 狙 vs 步枪:Liquipedia 的 roles 是按主次排列的,取第一个打法标签即可。
        # 不能固定把 AWP 提到步枪前面——否则老一辈步枪手(coldzera、pashaBiceps、
        # SmithZz 等)生涯里兼职过狙,就会被误判成狙击手。
        for r in self.roles:
            lab = ROLE_LABEL.get(r)
            if lab in ("AWPer", "Rifler"):
                return lab
        if any(ROLE_LABEL.get(r) == "Analyst" for r in self.roles):
            return "Analyst"
        return "?"

    @property
    def role_set(self) -> set:
        """反馈黄色用的角色集合,只允许白名单组合:
        {IGL} {AWPer} {Rifler} {Coach} {IGL,AWPer} {AWPer,Rifler}。
        指挥默认持步枪,所以 IGL 不与 Rifler 构成混合;教练不参与混合。"""
        primary = self.primary_role
        if primary not in ANSWER_ROLES:
            return set()
        roles = {primary}
        labels = {ROLE_LABEL[r] for r in self.roles if r in ROLE_LABEL}
        if primary in ("IGL", "Rifler") and "AWPer" in labels:
            roles.add("AWPer")
        elif primary == "AWPer" and "Rifler" in labels:
            roles.add("Rifler")
        return roles

    @property
    def is_coach(self) -> bool:
        return self.is_head_coach

    @property
    def is_head_coach(self) -> bool:
        # 人工层显式指定 Coach 时以人工为准:上游把人挂成助教/无角色,
        # 但公认就是这队主教练的情况(S0tF1k@Spirit),否则会被下面
        # 的 team_resolution 判成非主教练而清空战队,变成"自由身教练"。
        # game_role 只有 override 能填 Coach——played_role 回退永远
        # 只产出 IGL/AWPer/Rifler,不会误触发。
        if self.game_role == "Coach":
            return True
        if self.team_resolution:
            return self.team_resolution in {
                "single_current_head_coach_team",
                "newest_current_head_coach_team",
                "head_coach_top_level_fallback",
            }
        return any(r in HEAD_COACH_ROLES for r in self.roles)

    @property
    def is_staff(self) -> bool:
        return self.is_head_coach or any(r in STAFF_ROLES for r in self.roles)

    @property
    def played_role(self) -> str:
        """选手时期的打法位置(忽略教练/经理等职务角色)。"""
        if "igl" in self.roles:
            return "IGL"
        # 同 primary_role:按 Liquipedia 原始顺序取第一个打法标签,不硬提 AWP
        for r in self.roles:
            lab = ROLE_LABEL.get(r)
            if lab in ("AWPer", "Rifler"):
                return lab
        return ""

    @property
    def is_searchable(self) -> bool:
        """Reject all-empty unresolved nickname stubs, but keep real profiles."""
        return bool(
            self.nickname
            and (
                self.real_name
                or self.country
                or self.birth_date
                or self.roles
                or self.majors_count
            )
        )

    @property
    def is_game_ready(self) -> bool:
        """Minimum attribute completeness required for becoming a puzzle answer."""
        return bool(
            self.nickname
            and self.country
            and self.birth_date
            and self.primary_role in ANSWER_ROLES
        )

    def age(self, today: date | None = None) -> int | None:
        return _age(self.birth_date, today or date.today())

    @property
    def is_active(self) -> bool:
        # 游戏里的“现役”指当前正式选手阵容，不是历史题库成员或组织雇员。
        return bool(
            self.team
            and not self.is_staff
            and (self.status or "").lower() != "retired"
        )

    @property
    def team_label(self) -> str:
        """无战队统一显示"自由身":退役/未签约/玩票的界线无法可靠维护,
        也不该成为对局反馈维度(在编与否才是可查证的事实)。"""
        return self.team or "自由身"

    @property
    def display_country(self) -> str:
        return CHINA_COUNTRY_LABELS.get(self.country, self.country or "")

    @property
    def nationality_key(self) -> str:
        """用于游戏判定的国籍；港澳台与中国大陆统一判定为中国。"""
        if self.country in CHINA_COUNTRY_LABELS:
            return "China"
        return self.country or ""

    @property
    def flag_country(self) -> str:
        """国籍栏使用国旗；中国大陆、香港、澳门、台湾统一使用中国国旗。"""
        if self.country in CHINA_COUNTRY_LABELS:
            return "China"
        return self.country or ""

    def brief(self) -> dict:
        """What the autocomplete list needs."""
        return {
            "page": self.page,
            "nickname": self.nickname,
            "real_name": self.real_name,
            "country": self.display_country,
            "team": self.team,
            "majors_count": self.majors_count or 0,
            "majors_won": self.majors_won,
            "photo": self.photo,
            "flag": self.flag,
            "team_logo": self.team_logo,
        }

    def full(self, today: date | None = None) -> dict:
        return {
            "page": self.page,
            "nickname": self.nickname,
            "real_name": self.real_name,
            "country": self.display_country,
            "region": self.region,
            "age": self.age(today),
            "team": self.team or "",
            "team_label": self.team_label,
            "role": self.primary_role,
            "majors_count": self.majors_count or 0,
            "majors_won": self.majors_won,
            "status": self.status,
            "active": self.is_active,
            "photo": self.photo,
            "flag": self.flag,
            "team_logo": self.team_logo,
            "hltv_url": self.hltv_url,
        }


class PlayerDB:
    def __init__(self, path: Path = DATA_PATH):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.generated_at = raw.get("generated_at", "")
        self.ranking = TeamRanking()
        self.major_results = load_major_results()
        override_raw = _read_json(overrides_path())
        overrides = {k.casefold(): v for k, v in override_raw.items()}
        if IMAGES_PATH.exists():
            img = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
        else:
            img = {}
        self.manual_photo_map = _read_json(MANUAL_IMAGES_PATH).get("players", {})
        self.photo_map = img.get("players", {})
        self.team_logo_map = img.get("teams", {})
        self.team_logo_by_key = {
            normalize_team_name(team): logo
            for team, logo in self.team_logo_map.items()
        }
        self.flag_map = img.get("flags", {})
        self.excluded_stubs = 0
        self.players = []
        # 人工记录同 page 时就地替换爬取记录(保持原顺序),否则追加到末尾。
        manual = {str(r["page"]).casefold(): r for r in manual_records()}
        used: set[str] = set()
        records: list[tuple[dict, bool]] = []
        for rec in raw["players"]:
            key = str(rec.get("page", "")).casefold()
            if key in manual:
                used.add(key)
                records.append((manual[key], True))
            else:
                records.append((rec, False))
        records += [(r, True) for k, r in manual.items() if k not in used]
        for rec, is_manual in records:
            merged = dict(rec)
            override = overrides.get(str(rec.get("page", "")).casefold(), {})
            for key in ("team", "status", "game_role", "birth_date"):
                if key in override:
                    merged[key] = override[key]
            merged["majors"] = apply_major_results(
                merged.get("majors"), self.major_results)
            p = Player(merged, is_manual)
            if p.is_staff and not p.is_head_coach:
                # 主教练保留当前战队；助教和其他职务显示自由身。
                p.team = ""
            if p.team:
                # 榜单中的战队统一使用快照规范名，避免同队别名在界面上分裂。
                p.team = self.ranking.canonical_name(p.team) or p.team
            if (p.game_role not in ANSWER_ROLES
                    and p.primary_role not in ("IGL", "AWPer", "Rifler")
                    and not p.is_head_coach):
                # 助教/分析师/经理/解说和空角色老选手回退到选手时期位置；
                # 当前主教练则保留 Coach。
                fallback = override.get("played_role") or p.played_role
                if fallback:
                    p.game_role = fallback
            if not p.is_searchable:
                self.excluded_stubs += 1
                continue
            self.players.append(p)
        self.answer_players = [p for p in self.players if p.is_game_ready]
        for p in self.players:
            # 后台上传的照片优先:人工新增的人上游没有图,已有选手换图也走这条。
            p.photo = (_manual_img(self.manual_photo_map.get(p.page))
                       or _img(self.photo_map.get(p.page)))
            p.team_logo = _img(
                self.team_logo_map.get(p.team or "")
                or self.team_logo_by_key.get(normalize_team_name(p.team or "")))
            p.flag = _img(self.flag_map.get(p.flag_country))
        if HLTV_MAP_PATH.exists():
            hltv = json.loads(HLTV_MAP_PATH.read_text(encoding="utf-8"))
            hltv_map = {k.casefold(): v for k, v in hltv.get("players", {}).items()}
            for p in self.players:
                m = hltv_map.get((p.page or "").casefold())
                if m and m.get("hltv_id") and m.get("slug"):
                    p.hltv_url = (f"https://www.hltv.org/player/"
                                  f"{m['hltv_id']}/{m['slug']}")
        self.by_page = {p.page: p for p in self.players}
        self.by_nick: dict[str, list] = {}
        for p in self.players:
            self.by_nick.setdefault(p.nickname.lower(), []).append(p)
        # HLTV 年度 Top20 快照:历年上榜选手合并成一个去重明星池
        self.top20_pool: list = []
        if TOP20_PATH.exists():
            snap = json.loads(TOP20_PATH.read_text(encoding="utf-8"))
            seen = set()
            for year in sorted(snap.get("years", {})):
                for x in snap["years"][year]:
                    p = self.by_page.get(x.get("page"))
                    if p and p.is_game_ready and p.page not in seen:
                        seen.add(p.page)
                        self.top20_pool.append(p)

    @staticmethod
    def _fame(p) -> tuple:
        return (p.is_game_ready, p.majors_count or 0, p.in_blast_pool)

    def lookup(self, name: str) -> Player | None:
        """Resolve a guess string (page id or nickname) to a player.

        同名时优先知名度高的(Major 场次多 / 现役)。
        """
        if not name:
            return None
        name = name.strip()
        if name in self.by_page:
            return self.by_page[name]
        key = name.lower()
        hits = self.by_nick.get(key)
        if hits:
            return max(hits, key=self._fame)
        page_hits = [p for p in self.players if p.page.lower() == key]
        if page_hits:
            return page_hits[0]
        # 用真实姓名猜:输入的每个词都要出现在选手本名里(至少两个词,防误匹配)
        qt = _fold(name).split()
        if len(qt) >= 2:
            real_hits = [p for p in self.players
                         if set(qt) <= set(_fold(p.real_name).split())]
            if real_hits:
                return max(real_hits, key=self._fame)
        pref = [p for p in self.players if p.nickname.lower().startswith(key)]
        if pref:
            if len({p.page for p in pref}) == 1:
                return pref[0]
            return None
        return None

    # ------------------------------------------------------------- pools
    def difficulty_pool(self, difficulty: str) -> list:
        if difficulty == "top20":
            return list(self.top20_pool)
        if difficulty == "easy":
            return [p for p in self.answer_players
                    if (p.majors_count or 0) >= 4
                    or (p.in_blast_pool and (p.majors_count or 0) >= 2)]
        if difficulty == "medium":
            return [p for p in self.answer_players
                    if (p.majors_count or 0) >= 2 or p.in_blast_pool]
        return list(self.answer_players)

    def filter_pool(self, settings: dict) -> list:
        pool = self.difficulty_pool(settings.get("difficulty", "medium"))
        regions = settings.get("regions") or []
        if regions:
            pool = [p for p in pool if p.region in regions]
        if settings.get("active_only"):
            pool = [p for p in pool if p.is_active]
        y0 = settings.get("year_from")
        y1 = settings.get("year_to")
        if y0 or y1:
            def in_era(p):
                a = p.first_major_year or 2026   # blast-only rookies: current era
                b = p.last_major_year or 2026
                return (not y1 or a <= y1) and (not y0 or b >= y0)
            pool = [p for p in pool if in_era(p)]
        # a puzzle needs at least a couple of candidates
        return pool
