#!/usr/bin/env python
"""Write the chunks Zarr left out, so every store reads without listing rights.

Zarr does not write a chunk that holds only the fill value; a reader that asks
for it is expected to get "not found" and use the fill value. An object store
that lets anonymous users read objects but not list the bucket answers such a
request with 403 instead, which zarr treats as an error, so a public store
with skipped chunks cannot be read in full. Writing those chunks — a few
hundred bytes each once compressed — makes every key exist.

Every Zarr v3 store under each root is checked; stores with every chunk
present are left untouched.

Usage:
  python fill_empty_chunks.py s3://my-bucket/munkholmen/products s3://my-bucket/munkholmen/sv
"""

from __future__ import annotations

import argparse
import itertools
import math

import numpy as np
import zarr

from storage import filesystem, s3_options


def store_roots(fs, root: str) -> dict[str, set[str]]:
    """Each ``*.zarr`` store under *root*, with the keys it holds, relative to it."""
    stores: dict[str, set[str]] = {}
    for path in fs.find(root):
        head, sep, key = path.partition(".zarr/")
        if sep:
            stores.setdefault(head + ".zarr", set()).add(key)
    return stores


def open_store(path: str, s3: bool):
    if s3:
        return zarr.storage.FsspecStore.from_url(f"s3://{path}", storage_options=s3_options())
    return zarr.storage.LocalStore(path)


def fill(store, keys: set[str], dry_run: bool = False) -> int:
    """Write the missing chunks of every array in *store*; returns how many."""
    group = zarr.open_group(store, mode="r" if dry_run else "r+", zarr_format=3)
    written = 0
    for name, array in group.members(max_depth=None):
        if not isinstance(array, zarr.Array) or array.ndim == 0 or 0 in array.shape:
            continue
        # The stored objects are shards when the array is sharded.
        block = array.shards or array.chunks
        grid = [range(math.ceil(s / b)) for s, b in zip(array.shape, block)]
        for coords in itertools.product(*grid):
            key = f"{name}/{array.metadata.encode_chunk_key(coords)}"
            if key in keys:
                continue
            written += 1
            if dry_run:
                continue
            region = tuple(
                slice(c * b, min((c + 1) * b, s)) for c, b, s in zip(coords, block, array.shape)
            )
            shape = tuple(r.stop - r.start for r in region)
            array[region] = np.full(shape, array.fill_value, dtype=array.dtype)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="+", help="Directories or s3:// prefixes holding Zarr stores")
    parser.add_argument("--dry-run", action="store_true", help="Count the missing chunks, write nothing")
    args = parser.parse_args()

    # Without this zarr would skip the very chunks it is asked to write.
    with zarr.config.set({"array.write_empty_chunks": True}):
        for root in args.roots:
            fs, path = filesystem(root)
            total = 0
            stores = store_roots(fs, path)
            for store_path, keys in sorted(stores.items()):
                written = fill(open_store(store_path, root.startswith("s3://")), keys, args.dry_run)
                if written:
                    print(f"  {store_path.removeprefix(path + '/')}: {written} chunk(s) missing")
                total += written
            done = "counted" if args.dry_run else "written"
            print(f"{root}: {len(stores)} store(s), {total} missing chunk(s) {done}")


if __name__ == "__main__":
    main()
