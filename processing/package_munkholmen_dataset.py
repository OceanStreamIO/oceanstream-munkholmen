#!/usr/bin/env python
"""Assemble the Munkholmen April 2026 products.

By default the products are written to ``../outputs`` in this repository:
the EK80 MVBS (per day and for the whole campaign), the MVBS echograms, the
ADCP/CTD products and the recording-gap table, with a ``MANIFEST.csv`` of
sizes and SHA-256 checksums. The full-resolution Sv is not included.

Each MVBS Zarr store is written as a ``.zarr.zip`` (readable in place with
``zarr.storage.ZipStore``), because Zenodo stores flat files; the campaign
MVBS is also written as NetCDF.

With ``--standalone`` the folder also receives the dataset README and a copy
of the processing files, which makes it the self-contained Zenodo deposit.

Usage:
  python package_munkholmen_dataset.py --root ~/data/munkholmen_2026
  python package_munkholmen_dataset.py --root ~/data/munkholmen_2026 \
      --standalone --out ~/data/munkholmen_2026/zenodo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PROCESSING_FILES = (
    "run-munkholmen-apr2026.sh",
    "munkholmen_denoise.toml",
    "process_munkholmen_sensors.py",
    "export_ping_gaps.py",
    "package_munkholmen_dataset.py",
)


# Buoy position: 63° 27.45' N, 010° 22.33' E
DATASET_ATTRS = {
    "title": "EK80 MVBS, SINTEF OceanLab Munkholmen buoy, Trondheim Fjord, April 2026",
    "platform": "SINTEF OceanLab Munkholmen buoy (stationary, transducer in the moonpool)",
    "instrument": "Simrad EK80 WBT Mini 274022, ES38-18|200-18CR, 38 and 200 kHz CW",
    "geospatial_lat": 63.4575,
    "geospatial_lon": 10.3722,
    "transducer_depth_m": 0.0,
    "license": "CC0-1.0",
}


def export_mvbs(store: Path, dest_zip: Path, dest_nc: Path | None = None) -> None:
    """Write an MVBS store with the site metadata as a zipped Zarr (and NetCDF)."""
    import xarray as xr
    import zarr

    import numpy as np

    ds = xr.open_zarr(store).load()
    # Day stores are split by raw-file start time, so the bin at a day boundary
    # exists in both neighbours. Merge the two halves (linear-domain mean).
    times = ds["ping_time"].values
    if len(np.unique(times)) < len(times):
        linear = (10 ** (ds["Sv"] / 10)).groupby("ping_time").mean()
        merged = (10 * np.log10(linear)).transpose(*ds["Sv"].dims)
        merged.attrs = ds["Sv"].attrs
        ds = ds.drop_vars("Sv").drop_duplicates("ping_time").assign(Sv=merged)
    ds.attrs.update(DATASET_ATTRS)
    for name in list(ds.variables):
        ds[name].encoding.clear()
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    zip_store = zarr.storage.ZipStore(dest_zip, mode="w")
    ds.to_zarr(zip_store, mode="w", consolidated=False)
    zip_store.close()
    if dest_nc is not None:
        encoding = {v: {"zlib": True, "complevel": 4} for v in ds.data_vars if ds[v].ndim >= 2}
        ds.to_netcdf(dest_nc, encoding=encoding)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(name: str) -> str:
    return name.replace("|", "-").replace(" ", "_")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.home() / "data/munkholmen_2026")
    parser.add_argument("--container", default="ek80")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "outputs")
    parser.add_argument("--standalone", action="store_true",
                        help="Also add the dataset README and the processing files (Zenodo deposit)")
    args = parser.parse_args()

    root = args.root.expanduser()
    container = root / args.container
    out = args.out.expanduser()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # EK80 MVBS stores and MVBS echograms
    for store in sorted(container.rglob("*mvbs*.zarr")):
        if any(parent.suffix == ".zarr" for parent in store.parents):
            continue
        campaign = store.name.startswith("campaign_")
        sub = "campaign" if campaign else store.parent.name
        dest = out / "ek80" / sub / (store.name + ".zip")
        print(f"mvbs {store.relative_to(container)}")
        export_mvbs(store, dest, dest.with_name(store.stem + ".nc") if campaign else None)
    for png in sorted(container.rglob("*.png")):
        rel = png.relative_to(container)
        if "mvbs" not in png.name:
            continue
        sub = "campaign" if rel.parts[0] == "campaign" else rel.parts[0]
        dest = out / "ek80" / sub / "echograms" / _safe_name(png.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(png, dest)

    # ADCP / CTD products and the gap table
    sensors = root / "sensors"
    if sensors.is_dir():
        for sub in ("adcp", "ctd"):
            if (sensors / sub).is_dir():
                shutil.copytree(sensors / sub, out / sub)
    gaps = root / "ek80_recording_gaps.csv"
    if gaps.exists():
        shutil.copy2(gaps, out / "ek80" / gaps.name)

    if args.standalone:
        proc = out / "processing"
        proc.mkdir()
        for name in PROCESSING_FILES:
            shutil.copy2(SCRIPT_DIR / name, proc / name)
        shutil.copy2(REPO_ROOT / "requirements.txt", out / "requirements.txt")
        shutil.copy2(REPO_ROOT / "metadata" / "dataset_README.md", out / "README.md")

    files = sorted(p for p in out.rglob("*") if p.is_file())
    with open(out / "MANIFEST.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["path", "size_bytes", "sha256"])
        for path in files:
            writer.writerow([path.relative_to(out).as_posix(), path.stat().st_size, sha256(path)])

    total = sum(p.stat().st_size for p in files)
    print(f"\n{len(files)} files, {total / 1e9:.2f} GB → {out}")


if __name__ == "__main__":
    main()
