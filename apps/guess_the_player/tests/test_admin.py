# -*- coding: utf-8 -*-
"""管理页接口:鉴权开关 / 反馈收件箱 / override 编辑 / 热重载 / 体检 /
staging 发布 / 维护任务 / HLTV 审核。"""
import base64
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from playerdb import players
from server import admin, main


class AdminDisabledTests(unittest.TestCase):
    """未配置 ADMIN_TOKEN 时,管理入口必须整体不存在。"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        self._old = main.config.ADMIN_TOKEN
        main.config.ADMIN_TOKEN = ""

    def tearDown(self):
        main.config.ADMIN_TOKEN = self._old

    def test_admin_disabled_is_404(self):
        self.assertEqual(self.client.get("/admin").status_code, 404)
        self.assertEqual(self.client.get("/api/admin/ping").status_code, 404)
        self.assertEqual(
            self.client.get("/api/admin/ping",
                            headers={"X-Admin-Token": "whatever"}).status_code,
            404)


class AdminApiTests(unittest.TestCase):
    TOKEN = "test-admin-token"

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        self._old = main.config.ADMIN_TOKEN
        main.config.ADMIN_TOKEN = self.TOKEN
        self.h = {"X-Admin-Token": self.TOKEN}

    def tearDown(self):
        main.config.ADMIN_TOKEN = self._old

    # ------------------------------------------------------------- auth
    def test_wrong_token_is_401(self):
        r = self.client.get("/api/admin/ping",
                            headers={"X-Admin-Token": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_ping_reports_db(self):
        r = self.client.get("/api/admin/ping", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.json()["player_count"], 500)

    def test_admin_page_served_when_enabled(self):
        r = self.client.get("/admin")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])

    # --------------------------------------------------------- feedback
    def test_feedback_list_and_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = main.config.FEEDBACK_PATH
            main.config.FEEDBACK_PATH = Path(tmp) / "fb.jsonl"
            try:
                lines = [
                    json.dumps({"ts": "2026-07-20T10:00:00+0800", "ip": "1.1.1.1",
                                "page": "S1mple", "message": "年龄不对", "context": "daily"}),
                    "not json at all",
                    json.dumps({"ts": "2026-07-21T11:00:00+0800", "ip": "2.2.2.2",
                                "page": "", "message": "整体建议", "context": ""}),
                ]
                main.config.FEEDBACK_PATH.write_text(
                    "\n".join(lines) + "\n", encoding="utf-8")

                d = self.client.get("/api/admin/feedback", headers=self.h).json()
                self.assertEqual(len(d["entries"]), 2)      # 坏行被跳过
                self.assertEqual(d["open_count"], 2)
                # 新的在前;带 page 的条目解析出选手
                self.assertEqual(d["entries"][0]["message"], "整体建议")
                self.assertEqual(
                    d["entries"][1]["player"]["nickname"].lower(), "s1mple")

                fid = d["entries"][1]["id"]
                r = self.client.post(f"/api/admin/feedback/{fid}/state",
                                     headers=self.h,
                                     json={"resolved": True, "note": "已改生日"})
                self.assertEqual(r.status_code, 200)
                d = self.client.get("/api/admin/feedback", headers=self.h).json()
                self.assertEqual(d["open_count"], 1)
                got = next(e for e in d["entries"] if e["id"] == fid)
                self.assertTrue(got["resolved"])
                self.assertEqual(got["note"], "已改生日")
                # 状态落在旁路文件,原始 JSONL 不被改写
                self.assertEqual(
                    main.config.FEEDBACK_PATH.read_text(encoding="utf-8"),
                    "\n".join(lines) + "\n")

                r = self.client.post("/api/admin/feedback/ffffffffffff/state",
                                     headers=self.h,
                                     json={"resolved": True, "note": ""})
                self.assertEqual(r.status_code, 404)
            finally:
                main.config.FEEDBACK_PATH = old

    # ---------------------------------------------------------- players
    def test_search_players(self):
        d = self.client.get("/api/admin/players", headers=self.h,
                            params={"q": "s1mple"}).json()
        self.assertTrue(any(p["page"] == "S1mple" for p in d["players"]))
        # 真实姓名也能搜(变音符号折叠)
        d = self.client.get("/api/admin/players", headers=self.h,
                            params={"q": "kovac"}).json()
        self.assertTrue(any(p["nickname"].lower() == "niko" for p in d["players"]))

    def test_player_detail(self):
        d = self.client.get("/api/admin/players/S1mple", headers=self.h).json()
        self.assertEqual(d["effective"]["page"], "S1mple")
        self.assertIn("team", d["scraped"])
        self.assertIsInstance(d["feedback"], list)
        r = self.client.get("/api/admin/players/NoSuchPlayer999", headers=self.h)
        self.assertEqual(r.status_code, 404)

    def test_override_validation(self):
        url = "/api/admin/players/S1mple/override"
        cases = [
            ({"fields": {"team": "X"}, "reason": " "}, "reason"),
            ({"fields": {}, "reason": "r"}, "没有要覆盖"),
            ({"fields": {"country": "France"}, "reason": "r"}, "不支持"),
            ({"fields": {"game_role": "Sniper"}, "reason": "r"}, "game_role"),
            ({"fields": {"played_role": "Coach"}, "reason": "r"}, "played_role"),
            ({"fields": {"birth_date": "1997/10/02"}, "reason": "r"}, "birth_date"),
        ]
        for body, hint in cases:
            r = self.client.put(url, headers=self.h, json=body)
            self.assertEqual(r.status_code, 400, msg=str(body))
            self.assertIn(hint, r.json()["detail"])
        r = self.client.put("/api/admin/players/NoSuchPlayer999/override",
                            headers=self.h,
                            json={"fields": {"team": "X"}, "reason": "r"})
        self.assertEqual(r.status_code, 404)

    def test_override_write_reload_delete_roundtrip(self):
        old_path = players.OVERRIDES_PATH
        with tempfile.TemporaryDirectory() as tmp:
            players.OVERRIDES_PATH = Path(tmp) / "ov.json"
            players.OVERRIDES_PATH.write_text("{}", encoding="utf-8")
            try:
                r = self.client.put(
                    "/api/admin/players/S1mple/override", headers=self.h,
                    json={"fields": {"team": "AdminTest FC",
                                     "birth_date": "1999-01-02"},
                          "reason": "test roundtrip"})
                self.assertEqual(r.status_code, 200)
                saved = json.loads(
                    players.OVERRIDES_PATH.read_text(encoding="utf-8"))
                self.assertEqual(saved["S1mple"]["team"], "AdminTest FC")
                self.assertEqual(saved["S1mple"]["reason"], "test roundtrip")

                r = self.client.post("/api/admin/reload", headers=self.h)
                self.assertEqual(r.status_code, 200)
                d = self.client.get("/api/admin/players/S1mple",
                                    headers=self.h).json()
                self.assertEqual(d["effective"]["team"], "AdminTest FC")
                self.assertEqual(d["effective"]["birth_date"], "1999-01-02")
                self.assertEqual(d["override"]["team"], "AdminTest FC")

                r = self.client.delete("/api/admin/players/S1mple/override",
                                       headers=self.h)
                self.assertEqual(r.status_code, 200)
                r = self.client.delete("/api/admin/players/S1mple/override",
                                       headers=self.h)
                self.assertEqual(r.status_code, 404)
            finally:
                # 还原真实 overrides 并重载,避免污染同进程其他用例
                players.OVERRIDES_PATH = old_path
                self.client.post("/api/admin/reload", headers=self.h)
        d = self.client.get("/api/admin/players/S1mple", headers=self.h).json()
        self.assertNotEqual(d["effective"]["team"], "AdminTest FC")

    # ----------------------------------------------------------- health
    def test_health_categories(self):
        d = self.client.get("/api/admin/health", headers=self.h).json()
        for key in ("missing_birth_date", "missing_role", "missing_photo",
                    "missing_country", "age_anomaly", "not_game_ready",
                    "team_igl_conflict", "team_no_igl", "orphan_override"):
            self.assertIn(key, d["categories"])
            self.assertEqual(d["counts"][key], len(d["categories"][key]))
        self.assertGreater(d["player_count"], 500)

    def test_orphan_override_flagged(self):
        """override 以 page 名为键,上游改页名后会静默失效——必须报出来。"""
        from playerdb.players import Player

        roster = [Player({"page": "Rain", "nickname": "rain", "country": "X"})]
        self.assertEqual(
            admin.orphan_overrides(roster, {"Rain": {"game_role": "Rifler"}}), [])
        out = admin.orphan_overrides(
            roster, {"Rain (Norwegian player)": {"game_role": "Rifler"}})
        self.assertEqual([o["key"] for o in out], ["Rain (Norwegian player)"])

    def test_team_igl_conflicts_pure(self):
        from playerdb.players import Player

        def mk(page, team, roles, status="Active"):
            return Player({"page": page, "nickname": page, "country": "X",
                           "team": team, "status": status, "roles": roles})

        players = [
            mk("A", "T1", ["igl", "rifler"]),      # T1 双指挥 -> 都该报
            mk("B", "T1", ["igl", "entry"]),
            mk("C", "T1", ["awp"]),
            mk("D", "T2", ["igl"]),                # 单指挥,正常
            mk("E", "T3", ["igl"]),                # 同队但已退役,不算
            mk("F", "T3", ["igl"], status="Retired"),
            mk("G", "", ["igl"]),                  # 自由身不算
            mk("H", "T4", ["igl", "coach"]),       # 带教练职务 -> Coach,不算
            mk("I", "T4", ["coach", "igl"]),       # 同上
        ]
        got = {p.page for p in admin.team_igl_conflicts(players)}
        self.assertEqual(got, {"A", "B"})

    def test_teams_without_igl_pure(self):
        from playerdb.players import Player

        def mk(page, team, roles, status="Active"):
            return Player({"page": page, "nickname": page, "country": "X",
                           "team": team, "status": status, "roles": roles})

        def roster(prefix, team, roles_list, **kw):
            return [mk(f"{prefix}{i}", team, r, **kw)
                    for i, r in enumerate(roles_list)]

        players = [
            # T1:5 人首发没有任何 igl -> 整队都该报
            *roster("A", "T1", [["rifle"], ["awp"], ["entry"],
                                ["support"], ["lurker"]]),
            # T2:同样 5 人但有指挥 -> 正常
            *roster("B", "T2", [["igl"], ["awp"], ["entry"],
                                ["support"], ["lurker"]]),
            # T3:只有 3 个现役,残缺队史不算首发
            *roster("C", "T3", [["rifle"], ["awp"], ["entry"]]),
            # T4:4 人现役 + 教练;教练不占阵容位,仍算无指挥
            *roster("D", "T4", [["rifle"], ["awp"], ["entry"], ["support"]]),
            mk("D_coach", "T4", ["coach"]),
            # T5:够 4 人但全退役 -> 不算
            *roster("E", "T5", [["rifle"], ["awp"], ["entry"], ["support"]],
                    status="Retired"),
            # 自由身不参与分组
            mk("F", "", ["rifle"]),
        ]
        got = admin.teams_without_igl(players)
        self.assertEqual({p.team for p in got}, {"T1", "T4"})
        # 报的是整套阵容,不是单个人——指挥是谁只能人工判断
        self.assertEqual({p.page for p in got if p.team == "T1"},
                         {"A0", "A1", "A2", "A3", "A4"})
        # 教练不在现役阵容里,不该混进待判定的名单
        self.assertEqual({p.page for p in got if p.team == "T4"},
                         {"D0", "D1", "D2", "D3"})


def _fake_doc(*recs):
    return {"generated_at": "2026-07-23T00:00:00+00:00",
            "count": len(recs), "players": list(recs)}


def _rec(page, **kw):
    base = {"page": page, "nickname": page.lower(), "real_name": f"Real {page}",
            "country": "Denmark", "region": "Europe", "birth_date": "1995-05-05",
            "team": "TestTeam", "status": "Active", "roles": ["rifler"],
            "majors_count": 3, "in_blast_pool": False, "majors": []}
    base.update(kw)
    return base


class StagingTests(unittest.TestCase):
    TOKEN = "test-admin-token"

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        self._old_token = main.config.ADMIN_TOKEN
        main.config.ADMIN_TOKEN = self.TOKEN
        self.h = {"X-Admin-Token": self.TOKEN}

    def tearDown(self):
        main.config.ADMIN_TOKEN = self._old_token

    def test_diff_players_pure(self):
        cur = _fake_doc(_rec("A"), _rec("B", team="OldTeam"), _rec("C"))
        stg = _fake_doc(_rec("A"), _rec("B", team="NewTeam", majors_count=4),
                        _rec("D"))
        d = admin.diff_players(cur, stg)
        self.assertEqual(d["counts"], {"added": 1, "removed": 1, "changed": 1})
        self.assertEqual(d["added"][0]["page"], "D")
        self.assertEqual(d["removed"][0]["page"], "C")
        chg = d["changed"][0]
        self.assertEqual(chg["page"], "B")
        fields = {c["field"]: c for c in chg["changes"]}
        self.assertEqual(fields["team"]["new"], "NewTeam")
        self.assertEqual(fields["majors_count"]["old"], 3)

    def test_staging_missing_then_promote_roundtrip(self):
        old_data = players.DATA_PATH
        old_manual = players.MANUAL_PLAYERS_PATH
        with tempfile.TemporaryDirectory() as tmp:
            cur_path = Path(tmp) / "players.json"
            cur_doc = _fake_doc(_rec("A"), _rec("B"))
            cur_path.write_text(json.dumps(cur_doc), encoding="utf-8")
            players.DATA_PATH = cur_path
            # 人工新增层始终会并进任何 players.json,这里要一起隔离,
            # 否则真实的彩蛋选手会混进这套 2 人假数据里。
            players.MANUAL_PLAYERS_PATH = Path(tmp) / "manual.json"
            try:
                d = self.client.get("/api/admin/staging", headers=self.h).json()
                self.assertFalse(d["exists"])

                r = self.client.post("/api/admin/staging/promote",
                                     headers=self.h, json={"force": False})
                self.assertEqual(r.status_code, 404)

                stg_doc = _fake_doc(_rec("A", team="Moved FC"), _rec("B"),
                                    _rec("New1"))
                (Path(tmp) / "players.staging.json").write_text(
                    json.dumps(stg_doc), encoding="utf-8")
                d = self.client.get("/api/admin/staging", headers=self.h).json()
                self.assertTrue(d["exists"])
                self.assertEqual(d["count"], 3)
                self.assertEqual(d["diff"]["counts"],
                                 {"added": 1, "removed": 0, "changed": 1})

                r = self.client.post("/api/admin/staging/promote",
                                     headers=self.h, json={"force": False})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["promoted_count"], 3)
                # staging 被消费,旧库备份,正式库换成 staging 内容
                self.assertFalse((Path(tmp) / "players.staging.json").exists())
                bak = json.loads((Path(tmp) / "players.json.bak")
                                 .read_text(encoding="utf-8"))
                self.assertEqual(len(bak["players"]), 2)
                now = json.loads(cur_path.read_text(encoding="utf-8"))
                self.assertEqual(len(now["players"]), 3)
                # db 已热重载成 staging 内容
                self.assertEqual(r.json()["player_count"], 3)

                # 数量骤降防护:2 人 -> 1 人(<80%)须 force
                (Path(tmp) / "players.staging.json").write_text(
                    json.dumps(_fake_doc(_rec("A"))), encoding="utf-8")
                r = self.client.post("/api/admin/staging/promote",
                                     headers=self.h, json={"force": False})
                self.assertEqual(r.status_code, 409)
                r = self.client.post("/api/admin/staging/promote",
                                     headers=self.h, json={"force": True})
                self.assertEqual(r.status_code, 200)

                # 丢弃:没有 staging 时 404
                r = self.client.delete("/api/admin/staging", headers=self.h)
                self.assertEqual(r.status_code, 404)
            finally:
                players.DATA_PATH = old_data
                players.MANUAL_PLAYERS_PATH = old_manual
                self.client.post("/api/admin/reload", headers=self.h)
        d = self.client.get("/api/admin/ping", headers=self.h).json()
        self.assertGreater(d["player_count"], 500)

    def test_job_runner(self):
        d = self.client.get("/api/admin/jobs", headers=self.h).json()
        self.assertIn("running", d)
        r = self.client.post("/api/admin/jobs/nope", headers=self.h)
        self.assertEqual(r.status_code, 404)

        admin.JOBS["echo"] = lambda: [sys.executable, "-c",
                                      "print('hello-job')"]
        try:
            r = self.client.post("/api/admin/jobs/echo", headers=self.h)
            self.assertEqual(r.status_code, 200)
            for _ in range(100):
                d = self.client.get("/api/admin/jobs", headers=self.h).json()
                if not d["running"]:
                    break
                time.sleep(0.1)
            self.assertFalse(d["running"])
            self.assertEqual(d["returncode"], 0)
            self.assertIn("hello-job", "\n".join(d["log"]))
        finally:
            admin.JOBS.pop("echo", None)


class HltvReviewTests(unittest.TestCase):
    TOKEN = "test-admin-token"

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        self._old_token = main.config.ADMIN_TOKEN
        main.config.ADMIN_TOKEN = self.TOKEN
        self.h = {"X-Admin-Token": self.TOKEN}

    def tearDown(self):
        main.config.ADMIN_TOKEN = self._old_token

    @staticmethod
    def _review_doc():
        return {
            "schema_version": 1,
            "generated_at": "2026-07-23T00:00:00+00:00",
            "stopped_early": False,
            "players": [{
                "local_page": "S1mple", "nickname": "s1mple",
                "real_name": "Oleksandr Kostyliev", "country": "Ukraine",
                "team": "BC.Game Esports", "status": "Active",
                "local_roles": ["awp"], "current_inference": "AWPer",
                "match": None, "match_reason": "test", "profile":
                    {"profile_url": "https://www.hltv.org/player/7998/s1mple",
                     "recent_maps": 30, "sniping_score": 92},
                "igl_evidence": [], "manual_evidence": [],
                "suggestion": {"suggested_role": "AWPer",
                               "confidence": "high", "reason": "unit test"},
                "decision": None, "decision_field": "game_role",
                "error": None,
            }],
        }

    def test_review_missing(self):
        old = admin.HLTV_REVIEW_PATH
        admin.HLTV_REVIEW_PATH = Path(tempfile.gettempdir()) / "no-such-review.json"
        try:
            d = self.client.get("/api/admin/hltv/review", headers=self.h).json()
            self.assertFalse(d["exists"])
            r = self.client.post("/api/admin/hltv/apply", headers=self.h,
                                 json={"write": False})
            self.assertEqual(r.status_code, 404)
        finally:
            admin.HLTV_REVIEW_PATH = old

    def test_decision_and_apply_flow(self):
        old_review = admin.HLTV_REVIEW_PATH
        old_ov = players.OVERRIDES_PATH
        with tempfile.TemporaryDirectory() as tmp:
            admin.HLTV_REVIEW_PATH = Path(tmp) / "role_review.json"
            players.OVERRIDES_PATH = Path(tmp) / "ov.json"
            admin.HLTV_REVIEW_PATH.write_text(
                json.dumps(self._review_doc()), encoding="utf-8")
            players.OVERRIDES_PATH.write_text("{}", encoding="utf-8")
            try:
                d = self.client.get("/api/admin/hltv/review",
                                    headers=self.h).json()
                self.assertTrue(d["exists"])
                self.assertEqual(d["pending"], 1)

                r = self.client.put(
                    "/api/admin/hltv/review/S1mple/decision", headers=self.h,
                    json={"decision": "Sniper", "decision_field": "game_role"})
                self.assertEqual(r.status_code, 400)
                r = self.client.put(
                    "/api/admin/hltv/review/NoSuch/decision", headers=self.h,
                    json={"decision": "IGL", "decision_field": "game_role"})
                self.assertEqual(r.status_code, 404)

                r = self.client.put(
                    "/api/admin/hltv/review/S1mple/decision", headers=self.h,
                    json={"decision": "AWPer", "decision_field": "game_role"})
                self.assertEqual(r.status_code, 200)
                saved = json.loads(
                    admin.HLTV_REVIEW_PATH.read_text(encoding="utf-8"))
                self.assertEqual(saved["players"][0]["decision"], "AWPer")

                # 预览:不写文件
                d = self.client.post("/api/admin/hltv/apply", headers=self.h,
                                     json={"write": False}).json()
                self.assertEqual(d["changed"], 1)
                self.assertEqual(
                    players.OVERRIDES_PATH.read_text(encoding="utf-8"), "{}")

                # 写入:进 overrides,带 reason 和 hltv_profile
                d = self.client.post("/api/admin/hltv/apply", headers=self.h,
                                     json={"write": True}).json()
                self.assertEqual(d["changed"], 1)
                self.assertIn("reload", d)
                ov = json.loads(
                    players.OVERRIDES_PATH.read_text(encoding="utf-8"))
                self.assertEqual(ov["S1mple"]["game_role"], "AWPer")
                self.assertTrue(ov["S1mple"]["reason"]
                                .startswith("HLTV role review confirmed"))
                self.assertIn("hltv_profile", ov["S1mple"])

                # 再跑一次:已是该值,跳过
                d = self.client.post("/api/admin/hltv/apply", headers=self.h,
                                     json={"write": True}).json()
                self.assertEqual(d["changed"], 0)

                # 保护:已有不同人工角色时默认跳过,需显式 replace
                players.OVERRIDES_PATH.write_text(
                    json.dumps({"S1mple": {"game_role": "Rifler"}}),
                    encoding="utf-8")
                d = self.client.post("/api/admin/hltv/apply", headers=self.h,
                                     json={"write": True}).json()
                self.assertEqual(d["changed"], 0)
                self.assertTrue(any("跳过" in m for m in d["messages"]))
                d = self.client.post(
                    "/api/admin/hltv/apply", headers=self.h,
                    json={"write": True, "replace_existing": True}).json()
                self.assertEqual(d["changed"], 1)
            finally:
                admin.HLTV_REVIEW_PATH = old_review
                players.OVERRIDES_PATH = old_ov
                self.client.post("/api/admin/reload", headers=self.h)


class ManualPlayerTests(unittest.TestCase):
    """人工新增选手 + 头像上传。两者都只写 data/manual/,爬虫重建不受影响。"""

    TOKEN = "test-admin-token"
    # 只看魔数、不解码,所以合法头 + 垃圾负载就够测通路
    PNG = b"\x89PNG\r\n\x1a\n" + b"fake-payload"

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        self._old_token = main.config.ADMIN_TOKEN
        main.config.ADMIN_TOKEN = self.TOKEN
        self.h = {"X-Admin-Token": self.TOKEN}
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._old = (players.MANUAL_PLAYERS_PATH, players.MANUAL_IMAGES_PATH,
                     players.MANUAL_IMG_DIR)
        players.MANUAL_PLAYERS_PATH = tmp / "players_manual.json"
        players.MANUAL_IMAGES_PATH = tmp / "images_manual.json"
        players.MANUAL_IMG_DIR = tmp / "img"
        self.client.post("/api/admin/reload", headers=self.h)

    def tearDown(self):
        (players.MANUAL_PLAYERS_PATH, players.MANUAL_IMAGES_PATH,
         players.MANUAL_IMG_DIR) = self._old
        self.client.post("/api/admin/reload", headers=self.h)
        main.config.ADMIN_TOKEN = self._old_token
        self._tmp.cleanup()

    def _body(self, **kw):
        body = {"nickname": "jabitch", "real_name": "Jab Frog",
                "country": "Denmark", "birth_date": "1998-04-01",
                "team": "Green Dragon", "game_role": "Coach",
                "roles": ["coach"], "reason": "彩蛋选手"}
        body.update(kw)
        return body

    def test_create_reload_delete_roundtrip(self):
        r = self.client.post("/api/admin/manual", headers=self.h,
                             json=self._body())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["record"]["region"], "Europe")   # 国籍推赛区

        self.client.post("/api/admin/reload", headers=self.h)
        d = self.client.get("/api/admin/players/jabitch", headers=self.h).json()
        self.assertEqual(d["effective"]["role"], "Coach")
        self.assertTrue(d["effective"]["manual"])
        self.assertTrue(d["effective"]["game_ready"])   # 四项齐全,能当谜底
        self.assertEqual(d["scraped"]["country"], "Denmark")  # 回落到人工原始记录
        listed = self.client.get("/api/admin/manual", headers=self.h).json()
        self.assertEqual([p["page"] for p in listed["players"]], ["jabitch"])

        r = self.client.delete("/api/admin/manual/jabitch", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.client.post("/api/admin/reload", headers=self.h)
        self.assertEqual(
            self.client.get("/api/admin/players/jabitch",
                            headers=self.h).status_code, 404)

    def test_generated_players_json_untouched(self):
        """新增只写人工层——这正是 MachineWJQ 当初被整库重建冲掉的教训。"""
        before = players.DATA_PATH.read_bytes()
        self.client.post("/api/admin/manual", headers=self.h, json=self._body())
        self.assertEqual(players.DATA_PATH.read_bytes(), before)
        self.assertTrue(players.MANUAL_PLAYERS_PATH.exists())

    def test_duplicate_and_validation(self):
        r = self.client.post("/api/admin/manual", headers=self.h,
                             json=self._body(nickname="s1mple", page="S1mple"))
        self.assertEqual(r.status_code, 409)
        for bad, field in ((self._body(reason=""), "reason"),
                           (self._body(roles=["frog"]), "roles"),
                           (self._body(birth_date="1998/04/01"), "birth_date"),
                           (self._body(game_role="Frogger"), "game_role")):
            r = self.client.post("/api/admin/manual", headers=self.h, json=bad)
            self.assertEqual(r.status_code, 400, field)

    def test_country_is_canonicalised_and_unknown_rejected(self):
        r = self.client.post("/api/admin/manual", headers=self.h,
                             json=self._body(country="russia"))
        self.assertEqual(r.status_code, 200)
        rec = r.json()["record"]
        self.assertEqual((rec["country"], rec["region"]), ("Russia", "CIS"))
        self.client.delete("/api/admin/manual/jabitch", headers=self.h)

        r = self.client.post("/api/admin/manual", headers=self.h,
                             json=self._body(country="Wakanda"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("未知国籍", r.json()["detail"])

    def test_status_is_restricted_to_upstream_values(self):
        r = self.client.post("/api/admin/manual", headers=self.h,
                             json=self._body(status="Benched"))
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/admin/manual", headers=self.h,
                             json=self._body(status="Retired"))
        self.assertEqual(r.json()["record"]["status"], "Retired")

    def test_empty_query_lists_the_whole_database(self):
        """「选手编辑」一进去就该有列表,不必先想出一个搜索词。"""
        d = self.client.get("/api/admin/players?q=&limit=0",
                            headers=self.h).json()
        self.assertEqual(d["total"], len(d["players"]))
        self.assertGreater(d["total"], 500)
        capped = self.client.get("/api/admin/players?q=&limit=5",
                                 headers=self.h).json()
        self.assertEqual(len(capped["players"]), 5)
        self.assertEqual(capped["total"], d["total"])
        # 截断只是取前 N,排序本身(按名气)对两种 limit 完全一致
        self.assertEqual(capped["players"], d["players"][:5])
        self.assertGreaterEqual(min(p["majors_count"] for p in capped["players"]),
                                max(p["majors_count"] for p in d["players"][-5:]))

    def test_paging_walks_the_list_without_gaps_or_repeats(self):
        """翻页必须是同一个排序上的切片:漏人或重人比不分页更糟。"""
        full = self.client.get("/api/admin/players?q=&limit=0",
                               headers=self.h).json()
        walked = []
        for off in range(0, 150, 50):
            d = self.client.get(f"/api/admin/players?q=&limit=50&offset={off}",
                                headers=self.h).json()
            self.assertEqual(d["offset"], off)
            self.assertEqual(d["total"], full["total"])
            walked += d["players"]
        self.assertEqual(walked, full["players"][:150])

    def test_offset_past_the_end_returns_empty_not_error(self):
        """越界翻页(改了搜索词还停在第 8 页)只该翻出空页。"""
        d = self.client.get("/api/admin/players?q=&limit=50&offset=999999",
                            headers=self.h).json()
        self.assertEqual(d["players"], [])
        self.assertEqual(d["offset"], d["total"])
        neg = self.client.get("/api/admin/players?q=&limit=5&offset=-10",
                              headers=self.h).json()
        self.assertEqual(neg["offset"], 0)
        self.assertEqual(len(neg["players"]), 5)

    def test_edit_manual_record(self):
        self.client.post("/api/admin/manual", headers=self.h, json=self._body())
        r = self.client.put("/api/admin/manual/jabitch", headers=self.h,
                            json=self._body(team="Blue Dragon", reason="改队"))
        self.assertEqual(r.status_code, 200)
        self.client.post("/api/admin/reload", headers=self.h)
        d = self.client.get("/api/admin/players/jabitch", headers=self.h).json()
        self.assertEqual(d["effective"]["team"], "Blue Dragon")
        self.assertEqual(
            self.client.put("/api/admin/manual/nobody", headers=self.h,
                            json=self._body()).status_code, 404)

    def test_photo_upload_and_delete(self):
        self.client.post("/api/admin/manual", headers=self.h, json=self._body())
        self.client.post("/api/admin/reload", headers=self.h)
        payload = base64.b64encode(self.PNG).decode()

        r = self.client.put("/api/admin/players/jabitch/photo", headers=self.h,
                            json={"data": payload})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rel"], "players/jabitch.png")
        self.assertTrue((players.MANUAL_IMG_DIR / "players/jabitch.png").exists())

        self.client.post("/api/admin/reload", headers=self.h)
        d = self.client.get("/api/admin/players/jabitch", headers=self.h).json()
        self.assertTrue(d["effective"]["photo"].startswith("/img-manual/"))
        self.assertIn("?v=", d["effective"]["photo"])   # 内容哈希照样带上

        r = self.client.delete("/api/admin/players/jabitch/photo", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertFalse((players.MANUAL_IMG_DIR / "players/jabitch.png").exists())
        self.assertEqual(
            self.client.delete("/api/admin/players/jabitch/photo",
                               headers=self.h).status_code, 404)

    def test_photo_rejects_non_images(self):
        self.client.post("/api/admin/manual", headers=self.h, json=self._body())
        self.client.post("/api/admin/reload", headers=self.h)
        for data in ("not-base64!!",
                     base64.b64encode(b"GIF89a whatever").decode(),
                     base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * (2 << 20)).decode(),
                     ""):
            r = self.client.put("/api/admin/players/jabitch/photo",
                                headers=self.h, json={"data": data})
            self.assertEqual(r.status_code, 400, data[:20])

    def test_photo_overrides_scraped_photo(self):
        """人工照片对爬取来的选手同样生效,优先级更高。"""
        self.client.put("/api/admin/players/S1mple/photo", headers=self.h,
                        json={"data": base64.b64encode(self.PNG).decode()})
        self.client.post("/api/admin/reload", headers=self.h)
        d = self.client.get("/api/admin/players/S1mple", headers=self.h).json()
        self.assertTrue(d["effective"]["photo"].startswith("/img-manual/"))


if __name__ == "__main__":
    unittest.main()
