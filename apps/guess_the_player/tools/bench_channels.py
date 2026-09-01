# -*- coding: utf-8 -*-
"""横向对比多个渠道/模型在 cstrikle AI 回合上的表现。

读取一个 channels JSON(见 apps/guess_the_player/tools/channels.example.json),对每个渠道跑
若干场景 × 重复次数,复用已验证的 benchmark_reasoning.py(子进程 + 环境变量
覆盖),汇总:
  - 平均/最大耗时(速度)
  - native function calling 成功率(出现 guess tool 调用且无降级/报错)
  - 跟随最优解率(followed_solver)
  - 错误数

用法:
  python gtptools/bench_channels.py --channels apps/guess_the_player/tools/channels.json
  python gtptools/bench_channels.py --channels apps/guess_the_player/tools/channels.json \
      --scenarios 0 1 --repeat 2 --effort low
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "scripts" / "benchmark_reasoning.py"


def run_one(channel: dict, scenario: int, effort: str, repeat: int) -> list[dict]:
    """跑单渠道单场景 repeat 次,返回每次的 benchmark JSON。"""
    env = os.environ.copy()
    env["AI_BASE_URL"] = channel["base_url"]
    env["AI_API_KEY"] = channel["api_key"]
    env["AI_MODEL"] = channel["model"]
    env["AI_TOOLS_MODE"] = channel.get("tools_mode", "auto")
    env["AI_SEARCH_ENABLED"] = "0"  # 横评关搜索,速度只测模型本身
    # 可选参数:留空则不影响 benchmark 的命令行默认
    eff = channel.get("reasoning_effort", effort)
    thinking = channel.get("thinking", "disabled")
    if "reasoning_effort" in channel and not channel["reasoning_effort"]:
        # 显式空串:让 config 不发送该参数
        env["AI_REASONING_EFFORT"] = ""
        eff = effort  # benchmark CLI 仍需一个合法值,但 config 环境变量为空会覆盖
    out = []
    for _ in range(repeat):
        cmd = [
            sys.executable, str(BENCH),
            "--effort", eff,
            "--scenario", str(scenario),
            "--thinking", thinking,
        ]
        try:
            r = subprocess.run(cmd, env=env, capture_output=True, text=True,
                               timeout=120)
            line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
            data = json.loads(line)
        except Exception as e:  # noqa: BLE001
            data = {"error": f"{type(e).__name__}: {e}", "elapsed_seconds": None,
                    "event_types": [], "followed_solver": False}
        out.append(data)
    return out


def native_ok(rec: dict) -> bool:
    """native function calling 是否真正生效。"""
    ev = rec.get("event_types", [])
    return (
        rec.get("error") is None
        and "guess" in ev
        and "forced_guess" not in ev
        and "model_error" not in ev
    )


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK,避免中文乱码
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", required=True)
    ap.add_argument("--scenarios", type=int, nargs="+", default=[0, 1, 2, 3])
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--effort", default="low",
                    choices=("low", "medium", "high", "max"))
    args = ap.parse_args()

    channels = json.loads(Path(args.channels).read_text(encoding="utf-8"))
    rows = []
    for ch in channels:
        name = ch.get("name", ch["model"])
        recs = []
        for sc in args.scenarios:
            recs += run_one(ch, sc, args.effort, args.repeat)
        times = [r["elapsed_seconds"] for r in recs
                 if r.get("elapsed_seconds") is not None and r.get("error") is None]
        errs = [r for r in recs if r.get("error")]
        native = sum(native_ok(r) for r in recs)
        followed = sum(bool(r.get("followed_solver")) for r in recs)
        summary = {
            "channel": name,
            "model": ch["model"],
            "runs": len(recs),
            "avg_s": round(statistics.mean(times), 2) if times else None,
            "max_s": round(max(times), 2) if times else None,
            "native_tools": f"{native}/{len(recs)}",
            "followed_solver": f"{followed}/{len(recs)}",
            "errors": len(errs),
            "err_sample": (errs[0].get("error") if errs else None),
        }
        rows.append(summary)
        print(json.dumps(summary, ensure_ascii=False))

    # 汇总表
    print("\n" + "=" * 92)
    hdr = f"{'渠道/模型':30} {'平均s':>7} {'最大s':>7} {'native工具':>10} {'跟最优':>8} {'错误':>5}"
    print(hdr)
    print("-" * 92)
    for r in sorted(rows, key=lambda x: (x["avg_s"] is None, x["avg_s"] or 0)):
        print(f"{(r['channel'])[:30]:30} "
              f"{(r['avg_s'] if r['avg_s'] is not None else '-'):>7} "
              f"{(r['max_s'] if r['max_s'] is not None else '-'):>7} "
              f"{r['native_tools']:>10} {r['followed_solver']:>8} {r['errors']:>5}")
    print("=" * 92)


if __name__ == "__main__":
    main()
