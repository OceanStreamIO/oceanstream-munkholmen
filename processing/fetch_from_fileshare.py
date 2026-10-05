#!/usr/bin/env python
"""Copy files from an Azure file share to a local directory.

The raw data for this deployment sit on an Azure file share: the EK80 files
(``*.raw`` and their ``*.idx`` indexes) at the top level, the ADCP files in
``adcp/`` and the CTD logs in ``ctd/``. The EK80 pipeline reads the ``.raw``
files straight from the share, so only the small inputs need copying: the
``.idx`` files for ``export_ping_gaps.py`` and the ADCP/CTD files for
``process_munkholmen_sensors.py``.

The connection string is read from ``AZURE_STORAGE_CONNECTION_STRING``.
Files already present locally with the same size are skipped, so an
interrupted copy can be resumed.

Usage:
  python fetch_from_fileshare.py --share sintef-ek80-oceanlab --dest ~/data/raw \\
      --include '*.idx' --include 'adcp/*' --include 'ctd/*'
"""

from __future__ import annotations

import argparse
import fnmatch
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def list_share(share, root: str = "") -> list[tuple[str, int]]:
    """Every file under *root*, as ``(path relative to the share, size)``."""
    found, queue = [], [root]
    while queue:
        current = queue.pop(0)
        for item in share.get_directory_client(current).list_directories_and_files():
            path = f"{current}/{item['name']}".strip("/")
            if item.get("is_directory"):
                queue.append(path)
            else:
                found.append((path, item.get("size") or 0))
    return sorted(found)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--share", required=True, help="File share name")
    parser.add_argument("--path", default="", help="Directory within the share (default: its root)")
    parser.add_argument("--dest", type=Path, required=True, help="Local directory to copy into")
    parser.add_argument("--include", action="append", default=[],
                        help="Glob on the path relative to --path (repeatable; default: everything)")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    from azure.storage.fileshare import ShareServiceClient

    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
    if not connection_string:
        raise SystemExit("Set AZURE_STORAGE_CONNECTION_STRING to the storage account holding the share.")
    share = ShareServiceClient.from_connection_string(connection_string).get_share_client(args.share)

    prefix = args.path.strip("/")
    files = []
    for path, size in list_share(share, prefix):
        rel = path[len(prefix):].lstrip("/") if prefix else path
        if args.include and not any(fnmatch.fnmatch(rel, pattern) for pattern in args.include):
            continue
        files.append((path, rel, size))

    dest = args.dest.expanduser()
    todo = [(p, r, s) for p, r, s in files
            if not ((dest / r).is_file() and (dest / r).stat().st_size == s)]
    print(f"{len(files)} files ({sum(s for *_, s in files) / 1e9:.2f} GB) match; "
          f"{len(todo)} to copy into {dest}")

    def fetch(entry: tuple[str, str, int]) -> None:
        path, rel, _size = entry
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        with open(partial, "wb") as fh:
            share.get_file_client(path).download_file().readinto(fh)
        partial.replace(target)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for _ in pool.map(fetch, todo):
            pass
    print("done")


if __name__ == "__main__":
    main()
