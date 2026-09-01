# -*- coding: utf-8 -*-
"""One-off: convert the remaining PNG player photos to same-size WebP.

Liquipedia hands out cutout PNGs for a minority of players; storing
photographic content losslessly cost 17.5MB of the 38MB photo library
(largest single file: 935KB). WebP keeps the dimensions and the alpha
channel three quarters of them actually use, at roughly a twelfth of
the bytes.

Dimensions are NOT reduced: the end-of-game reveal card renders the
photo at 240px, so a 2x display still wants ~480px of the 600px source.

Idempotent. `fetch_images.py` converts on download from now on, so this
only needs to run once over a library scraped before that change.
"""
import json
import sys
from pathlib import Path


from .fetch_images import DATA, IMG, photo_to_webp


def main(dry_run: bool = False) -> None:
    images_path = DATA / "images.json"
    images = json.loads(images_path.read_text(encoding="utf-8"))
    players = images["players"]

    pngs = [(page, rel) for page, rel in players.items()
            if rel.lower().endswith(".png")]
    if not pngs:
        print("no png photos left, nothing to do")
        return
    before = sum((IMG / rel).stat().st_size
                 for _, rel in pngs if (IMG / rel).exists())
    print(f"{len(pngs)} png photos, {before / 1048576:.1f}MB")
    if dry_run:
        for page, rel in sorted(pngs, key=lambda r: -(IMG / r[1]).stat().st_size
                                if (IMG / r[1]).exists() else 0)[:10]:
            size = (IMG / rel).stat().st_size if (IMG / rel).exists() else 0
            print(f"  {size / 1024:7.0f}K  {rel}")
        print("(dry run, nothing written)")
        return

    after, failed = 0, []
    for page, rel in pngs:
        path = IMG / rel
        if not path.exists():
            continue
        new = photo_to_webp(path)
        if new == path:
            failed.append(rel)
            continue
        players[page] = f"players/{new.name}"
        after += new.stat().st_size

    images_path.write_text(
        json.dumps(images, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"converted {len(pngs) - len(failed)} photos: "
          f"{before / 1048576:.1f}MB -> {after / 1048576:.1f}MB")
    if failed:
        print(f"kept as png ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
