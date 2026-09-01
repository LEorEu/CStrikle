# -*- coding: utf-8 -*-
"""One-off: re-download player photos at 600px (they were fetched at 256px).

Team logos / flags untouched; images.json keys stay the same because the
destination filenames are unchanged.
"""
import sys
from pathlib import Path


import json

import httpx

from .fetch_images import (DATA, IMG, UA, download_all,
                                  get_infobox_images, get_thumb_urls, slug)


def main():
    data = json.loads((DATA / "players.json").read_text(encoding="utf-8"))
    players = data["players"]
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}

    with httpx.Client(headers=headers, timeout=60) as client:
        print("[1/3] player page infobox images ...")
        pimg = get_infobox_images(client, [p["page"] for p in players])
        print("[2/3] resolving 600px thumbnail urls ...")
        purl = get_thumb_urls(client, list(pimg.values()), width=600)

    print("[3/3] downloading ...")
    jobs = []
    for page, fn in pimg.items():
        url = purl.get(fn)
        if not url:
            continue
        ext = ".png" if ".png" in url.lower() else ".jpg"
        dest = IMG / "players" / (slug(page) + ext)
        dest.unlink(missing_ok=True)   # 强制覆盖旧的 256px 版本
        jobs.append((url, dest))
    done = download_all(jobs, headers)
    total = sum(p.stat().st_size for p in (IMG / "players").glob("*"))
    print(f"done: {len(done)}/{len(jobs)} photos, total {total/1e6:.1f} MB")


if __name__ == "__main__":
    main()
