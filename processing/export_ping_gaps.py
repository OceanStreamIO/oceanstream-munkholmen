#!/usr/bin/env python
"""List the recording gaps in a directory of EK80 raw files.

Ping times are read from the ``.idx`` index files written next to each
``.raw`` file, so no raw data is decoded. Every interval between consecutive
pings longer than ``--min-gap`` seconds is written to a CSV, classified as

  outage   longer than ``--outage-threshold`` seconds (power loss, restart)
  pause    shorter (e.g. a duty-cycle pause between ping bursts)

Usage:
  python export_ping_gaps.py --raw-dir ~/data/raw/ek80 --out gaps.csv
"""

from __future__ import annotations

import argparse
import csv
import struct
from datetime import datetime, timezone
from pathlib import Path

NT_EPOCH_OFFSET_S = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def read_idx_ping_times(path: Path) -> list[float]:
    """Return the POSIX timestamps of the IDX0 datagrams in one index file."""
    data = path.read_bytes()
    times, offset = [], 0
    while offset + 12 <= len(data):
        (length,) = struct.unpack_from("<i", data, offset)
        if length <= 0:
            break
        if data[offset + 4:offset + 8] == b"IDX0":
            low, high = struct.unpack_from("<II", data, offset + 8)
            times.append(((high << 32) | low) / 1e7 - NT_EPOCH_OFFSET_S)
        offset += length + 8
    return times


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-gap", type=float, default=5.0, help="Shortest gap to list (s)")
    parser.add_argument("--outage-threshold", type=float, default=30.0,
                        help="Gaps longer than this are classed as outages (s)")
    args = parser.parse_args()

    pings: list[tuple[float, str]] = []
    for idx in sorted(args.raw_dir.expanduser().glob("*.idx")):
        pings.extend((t, idx.stem) for t in read_idx_ping_times(idx))
    pings.sort()

    rows = []
    for (t0, f0), (t1, f1) in zip(pings, pings[1:]):
        gap = t1 - t0
        if gap > args.min_gap:
            rows.append({
                "gap_start_utc": _iso(t0),
                "gap_end_utc": _iso(t1),
                "duration_s": round(gap, 2),
                "type": "outage" if gap > args.outage_threshold else "pause",
                "last_file_before": f0,
                "first_file_after": f1,
            })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    outages = [r for r in rows if r["type"] == "outage"]
    print(f"{len(pings)} pings, {_iso(pings[0][0])} → {_iso(pings[-1][0])}")
    print(f"{len(rows)} gaps > {args.min_gap:g} s: {len(outages)} outages "
          f"({sum(r['duration_s'] for r in outages) / 60:.1f} min), "
          f"{len(rows) - len(outages)} pauses "
          f"({sum(r['duration_s'] for r in rows if r['type'] == 'pause') / 3600:.1f} h)")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
