# -*- coding: utf-8 -*-
"""
Fetch player photos, team logos and country flags for the cstrikle UI.

  - player photos: infobox |image= of each player page  (Liquipedia)
  - team logos:    infobox |image= of each current-team page (Liquipedia)
  - flags:         flagcdn.com w40 PNGs for all countries in the DB

Downloads 256px thumbnails into data/img/{players,teams,flags}/ and writes
data/images.json mapping. Re-runnable: existing files are skipped.

API usage follows Liquipedia terms (UA + rate limit); image thumbnails come
from the static CDN with modest throttling.
"""
import json
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from PIL import Image

from .build_db import API, RATE_SECONDS, UA, api_get  # noqa: E402

from ..paths import DATA, ROOT
IMG = DATA / "img"
BATCH = 50

TEAM_SKIP = {"", "retired", "inactive", "free agent", "freeagent"}


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:80] or "x"


def batched(seq, n=BATCH):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def api_get_retry(client, params, tries=3):
    for i in range(tries):
        try:
            return api_get(client, params)
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"  ! api error ({e}), retrying in 10s ...")
            time.sleep(10)


def get_infobox_images(client, titles, tpl_hint="Infobox"):
    """title -> image filename from its infobox |image= (first hit)."""
    out = {}
    for chunk in batched(titles):
        d = api_get_retry(client, {
            "action": "query", "titles": "|".join(chunk),
            "prop": "revisions", "rvprop": "content", "rvslots": "main",
            "redirects": "1",
        })
        q = d.get("query", {})
        back = {}
        for m in q.get("normalized", []) + q.get("redirects", []):
            back[m["to"]] = back.get(m["from"], m["from"])
        for page in q.get("pages", []):
            req = back.get(page["title"], page["title"])
            if page.get("missing"):
                continue
            try:
                content = page["revisions"][0]["slots"]["main"]["content"]
            except (KeyError, IndexError):
                continue
            # 文件名不能带 | = 等(有的页面 |image= 为空且与下个参数同行)
            m = re.search(r"^\|image\s*=\s*([^|\n{=]+?)\s*$", content, re.M) \
                or re.search(r"^\|image\s*=\s*([^|\n{=]+?)\s*\|", content, re.M)
            if m:
                fn = re.sub(r"<!--.*?-->", "", m.group(1)).strip()
                if fn and "." in fn:
                    out[req] = fn
        print(f"  infobox images {len(out)} collected ...")
    return out


COMMONS_API = "https://liquipedia.net/commons/api.php"
MODE_WORDS = {"full", "lightmode", "darkmode", "allmode", "std", "text"}
_commons_last = [0.0]


def commons_get(client, params):
    wait = RATE_SECONDS - (time.monotonic() - _commons_last[0])
    if wait > 0:
        time.sleep(wait)
    r = client.get(COMMONS_API, params={"format": "json", "formatversion": "2",
                                        **params})
    _commons_last[0] = time.monotonic()
    r.raise_for_status()
    return r.json()


def _core(name: str) -> str:
    stem = name.rsplit(".", 1)[0].replace("_", " ")
    return " ".join(w for w in stem.split() if w.lower() not in MODE_WORDS)


def pick_team_variant(client, filename: str) -> str:
    """挑最适合深色底的小图标:icon版 > 带文字full版;darkmode > allmode > lightmode。"""
    prefix = _core(filename)
    if not prefix:
        return filename
    try:
        d = commons_get(client, {"action": "query", "list": "allimages",
                                 "aiprefix": prefix, "ailimit": "50"})
        names = [x["name"].replace("_", " ")
                 for x in d.get("query", {}).get("allimages", [])]
    except Exception as e:
        print(f"  ! commons lookup failed for {prefix}: {e}")
        return filename
    cands = [n for n in names if _core(n) == prefix]
    if not cands:
        return filename

    def score(n):
        low = n.lower()
        s = 0
        if "full" in low or "text" in low:
            s += 10
        if "lightmode" in low:
            s += 3
        elif "allmode" in low:
            s += 1
        if not low.endswith(".png"):
            s += 5
        return s
    return min(cands, key=score)


def mode_tag(fn: str) -> str:
    low = fn.lower()
    if "darkmode" in low:
        return "_dm"
    if "lightmode" in low:
        return "_lm"
    return "_am"


def get_thumb_urls(client, filenames, width=256):
    """File name -> thumb url."""
    out = {}
    uniq = sorted(set(filenames))
    for chunk in batched(uniq):
        d = api_get_retry(client, {
            "action": "query",
            "titles": "|".join("File:" + f for f in chunk),
            "prop": "imageinfo", "iiprop": "url",
            "iiurlwidth": str(width),
        })
        q = d.get("query", {})
        norm = {m["to"]: m["from"] for m in q.get("normalized", [])}
        for page in q.get("pages", []):
            title = norm.get(page["title"], page["title"])
            name = title.split(":", 1)[-1]
            ii = (page.get("imageinfo") or [{}])[0]
            url = ii.get("thumburl") or ii.get("url")
            if url:
                out[name] = url
        print(f"  thumb urls {len(out)}/{len(uniq)}")
    return out


# 选手照片:Liquipedia 给的常是抠图 PNG,照片内容用无损格式存等于白扔几百 KB
# (全库最大的一张 935KB,转 WebP 后 56KB,同尺寸看不出差别)。不能转 JPEG——
# 四分之三的 PNG 真的带透明背景,转了会变成黑底方块。只处理照片:队标和国旗
# 本来就只有几 KB,转换省不下什么,却会让所有人的缓存失效。
PHOTO_WEBP_QUALITY = 82


def photo_to_webp(path: Path) -> Path:
    """PNG 照片就地转同尺寸 WebP,返回最终路径(非 PNG 或转换无收益则原样返回)。"""
    if path.suffix.lower() != ".png" or not path.exists():
        return path
    dest = path.with_suffix(".webp")
    try:
        with Image.open(path) as im:
            has_alpha = im.mode in ("RGBA", "LA") or (
                im.mode == "P" and "transparency" in im.info)
            im.convert("RGBA" if has_alpha else "RGB").save(
                dest, "WEBP", quality=PHOTO_WEBP_QUALITY, method=6)
    except Exception as e:
        print(f"  ! webp convert failed {path.name}: {e}")
        dest.unlink(missing_ok=True)
        return path
    if dest.stat().st_size >= path.stat().st_size:
        dest.unlink(missing_ok=True)      # 极少数已经很小的图,转了反而更大
        return path
    path.unlink()
    return dest


def photos_to_webp(players_map: dict) -> dict:
    """把 players_map 里的 PNG 全部转成 WebP,返回更新后的映射。"""
    out, saved = {}, 0
    for page, rel in players_map.items():
        path = IMG / rel
        new = photo_to_webp(path)
        if new != path:
            saved += 1
        out[page] = f"players/{new.name}"
    if saved:
        print(f"  converted {saved} png photos to webp")
    return out


def download_all(jobs, headers):
    """jobs: [(url, dest_path)] -> set of dest paths that exist afterwards."""
    ok = set()
    todo = [(u, p) for u, p in jobs if not p.exists()]
    for _, p in jobs:
        if p.exists():
            ok.add(p)

    def fetch(job):
        url, path = job
        try:
            with httpx.Client(headers=headers, timeout=30,
                              follow_redirects=True) as c:
                r = c.get(url)
                r.raise_for_status()
                path.write_bytes(r.content)
                time.sleep(0.15)
                return path
        except Exception as e:
            print(f"  ! download failed {path.name}: {e}")
            return None

    with ThreadPoolExecutor(3) as ex:
        for res in ex.map(fetch, todo):
            if res:
                ok.add(res)
    return ok


def main():
    for sub in ("players", "teams", "flags"):
        (IMG / sub).mkdir(parents=True, exist_ok=True)
    data = json.loads((DATA / "players.json").read_text(encoding="utf-8"))
    players = data["players"]
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}

    with httpx.Client(headers=headers, timeout=60) as client:
        print("[1/5] player page infobox images ...")
        pimg = get_infobox_images(client, [p["page"] for p in players])

        print("[2/5] team page infobox images ...")
        teams = sorted({p["team"] for p in players
                        if p["team"] and p["team"].lower() not in TEAM_SKIP})
        timg = get_infobox_images(client, teams)
        print("  optimizing team logo variants via commons ...")
        for i, (team, fn) in enumerate(list(timg.items()), 1):
            best = pick_team_variant(client, fn)
            if best != fn:
                timg[team] = best
            if i % 20 == 0:
                print(f"  variants {i}/{len(timg)}")

        print("[3/5] resolving thumbnail urls ...")
        # 600px:结算弹窗 230px 大图 + 高分屏需要,平均单张 ~80KB 可接受
        purl = get_thumb_urls(client, list(pimg.values()), width=600)
        turl = get_thumb_urls(client, list(timg.values()), width=120)

    print("[4/5] downloading ...")
    jobs, players_map, teams_map = [], {}, {}
    for page, fn in pimg.items():
        url = purl.get(fn)
        if not url:
            continue
        ext = ".png" if ".png" in url.lower() else ".jpg"
        dest = IMG / "players" / (slug(page) + ext)
        converted = dest.with_suffix(".webp")
        if ext == ".png" and converted.exists():
            # 上一轮已经转过 WebP,别再把同一张 PNG 重抓一遍
            players_map[page] = f"players/{converted.name}"
            continue
        jobs.append((url, dest))
        players_map[page] = f"players/{dest.name}"
    shutil.rmtree(IMG / "teams", ignore_errors=True)   # 变体可能更换,全量重下
    (IMG / "teams").mkdir(parents=True, exist_ok=True)
    for team, fn in timg.items():
        url = turl.get(fn)
        if not url:
            continue
        ext = ".png" if ".png" in url.lower() else ".jpg"
        dest = IMG / "teams" / (slug(team) + mode_tag(fn) + ext)
        jobs.append((url, dest))
        teams_map[team] = f"teams/{dest.name}"

    # flags from flagcdn (tiny, public)
    from .iso import ISO
    flags_map = {}
    for country in sorted({p["country"] for p in players if p["country"]}):
        iso = ISO.get(country)
        if not iso:
            continue
        dest = IMG / "flags" / f"{iso.lower()}.png"
        jobs.append((f"https://flagcdn.com/w40/{iso.lower()}.png", dest))
        flags_map[country] = f"flags/{iso.lower()}.png"

    done = download_all(jobs, headers)
    players_map = photos_to_webp(players_map)
    players_map = {k: v for k, v in players_map.items() if (IMG / v).exists()}
    teams_map = {k: v for k, v in teams_map.items() if (IMG / v).exists()}
    flags_map = {k: v for k, v in flags_map.items() if (IMG / v).exists()}

    print("[5/5] writing images.json ...")
    (DATA / "images.json").write_text(json.dumps({
        "players": players_map, "teams": teams_map, "flags": flags_map,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {len(players_map)} player photos, {len(teams_map)} team logos, "
          f"{len(flags_map)} flags, files={len(done)}")


if __name__ == "__main__":
    main()
