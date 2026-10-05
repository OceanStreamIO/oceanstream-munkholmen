#!/usr/bin/env python
"""Write a ≤2000 px preview next to every echogram PNG under a products root.

Full-resolution echogram panels run to ~14 500 px. The OceanStream Denoise
Lab viewer loads a preview first, written beside the panel as
``<name>--thumb.png``; this writes the same previews for a pipeline run made
outside the lab. Previews that already exist are kept.

The root is a local directory or an ``s3://bucket/prefix`` URI. For S3 the
endpoint comes from ``AWS_S3_ENDPOINT`` or ``S3_ENDPOINT_URL`` and the keys
from the usual ``AWS_*`` variables.

Usage:
  python make_thumbnails.py s3://bucket/munkholmen/products
  python make_thumbnails.py ~/data/munkholmen_2026/products
"""

from __future__ import annotations

import argparse
import io
from concurrent.futures import ThreadPoolExecutor

from storage import filesystem

THUMBNAIL_MAX_PX = 2000
THUMBNAIL_SUFFIX = "--thumb.png"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", help="Products root: a directory or s3://bucket/prefix")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    from PIL import Image

    # Panels legitimately run to tens of megapixels.
    Image.MAX_IMAGE_PIXELS = None

    fs, root = filesystem(args.root)
    pngs = set(fs.glob(f"{root}/**/*.png"))
    sources = sorted(p for p in pngs if not p.endswith(THUMBNAIL_SUFFIX))
    todo = [p for p in sources if p[: -len(".png")] + THUMBNAIL_SUFFIX not in pngs]
    print(f"{len(sources)} echograms, {len(todo)} without a preview")

    def thumbnail(path: str) -> None:
        with fs.open(path, "rb") as fh, Image.open(fh) as image:
            preview = image.copy()
        preview.thumbnail((THUMBNAIL_MAX_PX, THUMBNAIL_MAX_PX))
        buffer = io.BytesIO()
        preview.save(buffer, format="PNG", optimize=True)
        with fs.open(path[: -len(".png")] + THUMBNAIL_SUFFIX, "wb") as fh:
            fh.write(buffer.getvalue())

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for _ in pool.map(thumbnail, todo):
            pass
    print(f"wrote {len(todo)} previews")


if __name__ == "__main__":
    main()
