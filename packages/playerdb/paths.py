# -*- coding: utf-8 -*-
"""仓库里所有数据文件的唯一锚点。

搬成多包之前，每个模块各写各的 `Path(__file__).parent.parent / "data"`。
那种写法把「我在目录树的哪一层」焊死进了每个文件，模块一挪位置就集体指错，
而且错得很安静——读到的是不存在的路径，表现为「数据是空的」而不是报错。

所以只在这里算一次：从本文件往上找第一个含 `data/` 的目录当仓库根。装进
site-packages 或换部署布局时，用 `CSTRIKLE_DATA` 显式指定，不必改代码。
"""
import os
from pathlib import Path


def _resolve_data() -> Path:
    env = os.environ.get("CSTRIKLE_DATA")
    if env:
        return Path(env).resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "data").is_dir():
            return parent / "data"
    # 兜底:包被装到 site-packages 且没设环境变量时,至少给个确定的路径,
    # 让报错停在「文件不存在」而不是「路径莫名其妙」。
    return Path(__file__).resolve().parents[2] / "data"


DATA = _resolve_data()
ROOT = DATA.parent

#: Blind Draft 专属数据(卡库、队伍快照、5E 竞技数据与照片)
BLIND_DRAFT = DATA / "blind_draft"
#: 人工层:管理页唯一写盘的地方,生产上是挂载卷
MANUAL = DATA / "manual"
#: 选手照片 / 队标 / 国旗
IMG = DATA / "img"
