import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server import main


class ApiFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        # 匹配与限流都是进程内全局状态,逐用例清零避免互相污染
        main._match_waiters.clear()
        main._match_results.clear()
        main._feedback_attempts.clear()

    # ------------------------------------------------------------ top20
    def test_meta_exposes_top20_pool_size(self):
        sizes = self.client.get("/api/meta").json()["pool_sizes"]
        # 历年上榜合并去重:比单年 20 人多,比"简单"档小的全明星池
        self.assertGreater(sizes["top20"], 20)
        self.assertLess(sizes["top20"], sizes["easy"])

    def test_top20_game_uses_union_pool(self):
        sizes = self.client.get("/api/meta").json()["pool_sizes"]
        r = self.client.post("/api/game", json={
            "mode": "unlimited",
            "settings": {"difficulty": "top20"},
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pool_size"], sizes["top20"])

    def test_top20_pool_count_endpoint(self):
        sizes = self.client.get("/api/meta").json()["pool_sizes"]
        r = self.client.post("/api/pool_count", json={
            "settings": {"difficulty": "top20"},
        })
        self.assertEqual(r.json()["count"], sizes["top20"])

    # --------------------------------------------------------- feedback
    def test_feedback_written_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = main.config.FEEDBACK_PATH
            main.config.FEEDBACK_PATH = Path(tmp) / "fb.jsonl"
            try:
                r = self.client.post("/api/feedback", json={
                    "page": "S1mple", "message": "战队信息过时了",
                    "context": "daily",
                })
                self.assertEqual(r.status_code, 200)
                rec = json.loads(
                    main.config.FEEDBACK_PATH.read_text(encoding="utf-8")
                    .strip().splitlines()[-1])
                self.assertEqual(rec["page"], "S1mple")
                self.assertEqual(rec["context"], "daily")
            finally:
                main.config.FEEDBACK_PATH = old
        # 空反馈直接 400,不落盘不记日志
        r = self.client.post("/api/feedback", json={"message": "   "})
        self.assertEqual(r.status_code, 400)

    # ------------------------------------------------------ matchmaking
    def test_match_pairs_two_players(self):
        r1 = self.client.post("/api/match/join", json={"name": "甲"}).json()
        self.assertFalse(r1["matched"])
        r2 = self.client.post("/api/match/join", json={"name": "乙"}).json()
        self.assertTrue(r2["matched"])
        r3 = self.client.get(f"/api/match/poll/{r1['ticket']}").json()
        self.assertTrue(r3["matched"])
        self.assertEqual(r2["code"], r3["code"])
        self.assertNotEqual(r2["token"], r3["token"])
        room = main.rooms.get(r2["code"])
        self.assertEqual(room.status, "playing")
        self.assertEqual(room.settings["difficulty"], "medium")
        self.assertEqual(room.settings["game_seconds"], 120)
        # 两个 token 各对应一个真实座位
        self.assertIsNotNone(room.seat_by_token(r2["token"]))
        self.assertIsNotNone(room.seat_by_token(r3["token"]))

    def test_match_cancel_and_expiry(self):
        r1 = self.client.post("/api/match/join", json={"name": "甲"}).json()
        self.client.delete(f"/api/match/{r1['ticket']}")
        self.assertEqual(
            self.client.get(f"/api/match/poll/{r1['ticket']}").status_code, 404)
        # 取消后下一位进来重新排队,而不是跟幽灵配对
        r2 = self.client.post("/api/match/join", json={"name": "乙"}).json()
        self.assertFalse(r2["matched"])

    def test_match_same_name_disambiguated(self):
        self.client.post("/api/match/join", json={"name": "同名"})
        r2 = self.client.post("/api/match/join", json={"name": "同名"}).json()
        room = main.rooms.get(r2["code"])
        names = {s.name for s in room.seats()}
        self.assertEqual(len(names), 2)

    def test_match_never_pairs_across_difficulties(self):
        r1 = self.client.post("/api/match/join", json={
            "name": "甲", "difficulty": "top20"}).json()
        r2 = self.client.post("/api/match/join", json={
            "name": "乙", "difficulty": "medium"}).json()
        # 不同难度各自排队,谁都不该被配对
        self.assertFalse(r1["matched"])
        self.assertFalse(r2["matched"])
        # 同难度的第三人进来,只和 top20 队列里的甲配对
        r3 = self.client.post("/api/match/join", json={
            "name": "丙", "difficulty": "top20"}).json()
        self.assertTrue(r3["matched"])
        room = main.rooms.get(r3["code"])
        self.assertEqual(room.settings["difficulty"], "top20")
        self.assertEqual({s.name for s in room.seats()}, {"甲", "丙"})
        # 乙仍在常规队列等待
        self.assertFalse(
            self.client.get(f"/api/match/poll/{r2['ticket']}").json()["matched"])

    # ------------------------------------------------- leave after game over
    def _make_room(self):
        r = self.client.post("/api/room", json={
            "name": "甲", "settings": {"difficulty": "easy"},
            "vs_ai": False}).json()
        j = self.client.post(f"/api/room/{r['code']}/join",
                             json={"name": "乙"}).json()
        return r, j, main.rooms.get(r["code"])

    def test_leave_after_over_notifies_opponent_and_blocks_rematch(self):
        r, j, room = self._make_room()
        with self.client.websocket_connect(
                f"/ws/room/{r['code']}?token={r['token']}") as w1:
            w1.receive_json()          # 甲连上时的 state
            with self.client.websocket_connect(
                    f"/ws/room/{r['code']}?token={j['token']}") as w2:
                w1.receive_json()      # 乙连上触发的广播
                w2.receive_json()
                room.status = "over"
                room.winner = "甲"
                w2.send_json({"type": "leave"})
                # 留守的甲要收到系统聊天 + 标记对手不在场的新 state
                chat = w1.receive_json()
                self.assertEqual(chat["type"], "chat")
                self.assertIn("离开", chat["text"])
                state = w1.receive_json()
                self.assertEqual(state["type"], "state")
                self.assertFalse(state["opponent"]["present"])
            # 对手已离开,再来一局应被拒绝
            resp = self.client.post(f"/api/room/{r['code']}/rematch",
                                    headers={"X-Room-Token": r["token"]})
            self.assertEqual(resp.status_code, 409)

    def test_rematch_blocked_when_opponent_never_connected(self):
        r, j, room = self._make_room()
        room.status = "over"
        room.winner = "draw"
        # 乙的 ws 压根没连上(等同已跑路),甲不能对着空气重开
        resp = self.client.post(f"/api/room/{r['code']}/rematch",
                                headers={"X-Room-Token": r["token"]})
        self.assertEqual(resp.status_code, 409)


if __name__ == "__main__":
    unittest.main()
