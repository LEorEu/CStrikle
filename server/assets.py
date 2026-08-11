# -*- coding: utf-8 -*-
"""给页面里的静态资源 URL 加内容版本号。

站点在 Cloudflare 后面,/static/* 被 max-age=14400 缓存,而 HTML 不缓存
——发新版后浏览器会拿到新 HTML 配旧 JS,最长错配四个小时。真在这上面
栽过:把 COUNTRY_CN 抽成 countries.js 那次,浏览器缓存里的旧 app.js 顶层
还声明着同名 const,两个顶层 const 同名会让第二个脚本整体 SyntaxError,
页面直接白屏。

内容变 -> 哈希变 -> URL 变 -> 浏览器和 CDN 两层缓存同时失效,这类错配
就不存在了;内容没变则 URL 不变,重新部署刷掉时间戳也不会白白作废缓存。
和 players.py 给图片加 ?v= 是同一套做法。
"""
import hashlib
import re
from pathlib import Path

from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent.parent

# 任意属性都认(不止 src/href):换肤要把两张样式表的地址存在 data-v1/
# data-v2 上,那两个也必须带版本号,否则又是一条绕过缓存失效的暗道。
_ASSET_RE = re.compile(r'(?P<attr>[\w-]+)="(?P<url>/static/[^"?]+\.(?:js|css))"')
_HTML_CACHE: dict[Path, tuple[int, str]] = {}


def asset_version(url: str) -> str:
    target = ROOT / url.lstrip("/")
    try:
        return hashlib.blake2b(target.read_bytes(), digest_size=5).hexdigest()
    except OSError:
        return "0"


def versioned_html(path: Path) -> HTMLResponse:
    stamp = path.stat().st_mtime_ns
    cached = _HTML_CACHE.get(path)
    if cached is None or cached[0] != stamp:
        html = _ASSET_RE.sub(
            lambda m: f'{m["attr"]}="{m["url"]}?v={asset_version(m["url"])}"',
            path.read_text(encoding="utf-8"))
        _HTML_CACHE[path] = (stamp, html)
        cached = _HTML_CACHE[path]
    # HTML 本身必须不缓存,否则它引用的版本号也被冻住,等于没做。
    return HTMLResponse(cached[1],
                        headers={"Cache-Control": "no-cache, must-revalidate"})
