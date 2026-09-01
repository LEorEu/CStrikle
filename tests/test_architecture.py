# -*- coding: utf-8 -*-
"""包与包之间的依赖方向，用测试钉住。

这个仓库有两个游戏，共用一份选手库。拆包之前它们是缠在一起的：当时叫
`scripts/gen_draft_cards.py`（Blind Draft）的那个文件直接
`from server.players import PlayerDB`，于是 Blind Draft 的整套原型代码被
`COPY scripts ./scripts` 一路带进了猜选手的生产镜像。这类耦合不会让任何测试
变红，只会让镜像变大、让「改猜选手会不会弄坏 Blind Draft」变成一个没人
答得上来的问题。

所以写在这里：允许的方向只有一条，往下依赖共享底座，不许横着串。

    playerdb                    共享选手库，不依赖任何内部包
       ↑            ↑
    server ↔ gtptools        猜选手（互相依赖，同一个 app 内，允许）
    blinddraft ← bdtools     Blind Draft

两条硬约束：
  1. playerdb 不许依赖任何内部包——它是底座，谁都能用，它谁都不用。
  2. 猜选手一侧不许出现 blinddraft/bdtools——Dockerfile 靠这条才敢
     不把 apps/blind_draft 放进镜像。
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 包名 -> 源码目录（和 pyproject.toml 的 package-dir 映射保持一致）
PACKAGES = {
    "playerdb": "packages/playerdb",
    "server": "apps/guess_the_player/server",
    "gtptools": "apps/guess_the_player/tools",
    "blinddraft": "apps/blind_draft/blinddraft",
    "bdtools": "apps/blind_draft/tools",
    "bdserver": "apps/blind_draft/server",
}

#: 每个包允许依赖的内部包。没列出的一律算违规。
ALLOWED = {
    "playerdb": set(),
    "server": {"playerdb", "gtptools"},
    "gtptools": {"playerdb", "server"},
    "blinddraft": {"playerdb"},
    "bdtools": {"playerdb", "blinddraft"},
    # 调参后台。它读 blinddraft 的生成器、写 blinddraft 的人工层,但反过来
    # 不行:玩法代码一旦 import bdserver,命令行跑一局就要拖起 FastAPI。
    "bdserver": {"playerdb", "blinddraft"},
}


def internal_imports(pkg_dir: Path) -> dict:
    """包目录里每个文件 import 了哪些内部包 -> {包名: [出处]}。

    只看绝对 import：包内的相对 import（`from . import draft`）本来就合法，
    而且不跨包，不是这份测试要管的事。
    """
    out = {}
    for f in sorted(pkg_dir.rglob("*.py")):
        if "__pycache__" in f.parts or "tests" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top in PACKAGES:
                    out.setdefault(top, []).append(
                        "%s:%d" % (f.relative_to(ROOT).as_posix(), node.lineno))
    return out


class DependencyDirectionTests(unittest.TestCase):
    def test_no_package_reaches_outside_its_allowed_set(self):
        for pkg, rel in PACKAGES.items():
            with self.subTest(package=pkg):
                found = internal_imports(ROOT / rel)
                illegal = {k: v for k, v in found.items()
                           if k != pkg and k not in ALLOWED[pkg]}
                self.assertEqual(
                    illegal, {},
                    "%s 依赖了不该依赖的包。允许的是 %s；"
                    "要么改依赖方向，要么先想清楚再改 ALLOWED。"
                    % (pkg, sorted(ALLOWED[pkg]) or "（什么都不依赖）"))

    def test_playerdb_stays_a_base_layer(self):
        """底座不许反向依赖上层——否则 `import playerdb` 会把两个游戏都拖进来。"""
        found = internal_imports(ROOT / PACKAGES["playerdb"])
        self.assertEqual(
            {k: v for k, v in found.items() if k != "playerdb"}, {},
            "playerdb 是共享底座,不能依赖任何上层包")

    def test_guess_the_player_never_touches_blind_draft(self):
        """Dockerfile 不把 apps/blind_draft 放进镜像,靠的就是这条。"""
        for pkg in ("server", "gtptools"):
            found = internal_imports(ROOT / PACKAGES[pkg])
            leaked = {k: v for k, v in found.items()
                      if k in ("blinddraft", "bdtools")}
            self.assertEqual(
                leaked, {},
                "%s 引用了 Blind Draft(%s)。镜像里没有这些文件,线上会 "
                "ImportError——要么别引用,要么改 Dockerfile 一起 COPY 进去。"
                % (pkg, leaked))


class ImportSmokeTests(unittest.TestCase):
    def test_every_module_imports(self):
        """每个模块都 import 一遍。

        依赖方向那几条只看顶层包名,抓不到「子模块搬走了但引用没改」这类错——
        搬包时 `from server.players import PlayerDB` 就这么活下来了两轮:
        `server` 仍然是个合法的包,只是 `players` 已经不在里面。这种错要到真正
        执行那一行才炸,而那两个文件是手动跑的 benchmark,没有测试覆盖。
        """
        import importlib
        import pkgutil

        broken = []
        for name in PACKAGES:
            pkg = importlib.import_module(name)
            for info in pkgutil.walk_packages(pkg.__path__, name + "."):
                try:
                    importlib.import_module(info.name)
                except Exception as exc:                          # noqa: BLE001
                    broken.append("%s -> %s: %s"
                                  % (info.name, type(exc).__name__, exc))
        self.assertEqual(broken, [], "这些模块 import 就崩:\n  " + "\n  ".join(broken))


class PackageLayoutTests(unittest.TestCase):
    def test_pyproject_mapping_matches_this_file(self):
        """pyproject 的 package-dir 和上面那张表不许对不上。

        对不上的表现很难查:import 名还在,但指向另一个目录,这份测试会一直
        检查一个没人在跑的目录。
        """
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        block = text.split("[tool.setuptools.package-dir]")[1].split("[")[0]
        mapping = {}
        for line in block.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                mapping[k.strip()] = v.strip().strip('"')
        self.assertEqual(mapping, PACKAGES)

    def test_every_package_dir_exists(self):
        for pkg, rel in PACKAGES.items():
            with self.subTest(package=pkg):
                self.assertTrue((ROOT / rel / "__init__.py").is_file(),
                                "%s 缺 __init__.py：%s" % (pkg, rel))


if __name__ == "__main__":
    unittest.main()
