#!/usr/bin/env python
"""Publish the STAC catalogue of the Munkholmen products.

One STAC Item per day describes everything in ``products/<day>/`` — the
denoised, seabed-masked and pruned stores, the MVBS, the echograms — plus the
day's Sv store in ``sv/<day>/``. A Collection at ``products/collection.json``
lists the Items and carries the whole-deployment products and the files of
the packaged dataset as assets. The layout and the Item contents are those
of the OceanStream catalogues (``oceanstream.stac.echodata``), so the
OceanStream web app can import the Collection like any other.

The buoy is moored and the pings carry no positions, so every Item gets the
nominal buoy position as a Point.

In the bucket, hrefs are relative and ``self`` links absolute. With ``--copy``
the same documents are also written to a local directory with every href
made absolute, so they open from a clone of this repository.

Usage:
  python publish_stac.py --root s3://oceanstream-bucket/munkholmen \\
      --public-base https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen \\
      --copy ../stac
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from storage import filesystem, s3_options

COLLECTION_ID = "MUNKHOLMEN_2026"
BUOY = [10.3722, 63.4575]  # lon, lat: 63° 27.45' N, 010° 22.33' E
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TITLE = "Munkholmen buoy echosounder, ADCP and CTD, Trondheim Fjord, April 2026"
DESCRIPTION = (
    "Simrad EK80 WBT Mini (38 and 200 kHz CW) on the SINTEF OceanLab Munkholmen buoy, "
    "Trondheim Fjord, 10–14 April 2026: Sv at the full ping rate, the denoised, seabed-masked "
    "and pruned data (stored as masks over the Sv), MVBS and echograms for each day, the "
    "whole-deployment MVBS, and the ADCP and CTD products recorded alongside. Processed with "
    "the OceanStream batch pipeline; see "
    "https://github.com/OceanStreamIO/oceanstream-munkholmen."
)

# Collection-level assets: the whole deployment, and the packaged dataset's files.
COLLECTION_ASSETS = {
    "campaign_mvbs": ("./MUNKHOLMEN_2026/campaign_mvbs_short_pulse.zarr", "application/vnd+zarr",
                      ["data"], "MVBS, whole deployment (10 s × 0.5 m)"),
    "dataset_readme": ("../dataset/README.md", "text/markdown", ["metadata"],
                       "Dataset description: variables, processing, known limitations"),
    "dataset_manifest": ("../dataset/MANIFEST.csv", "text/csv", ["metadata"],
                         "Files of the packaged dataset, with sizes and SHA-256"),
    "campaign_mvbs_netcdf": ("../dataset/ek80/campaign/campaign_mvbs_short_pulse.nc",
                             "application/x-netcdf", ["data"], "MVBS, whole deployment, NetCDF"),
    "recording_gaps": ("../dataset/ek80/ek80_recording_gaps.csv", "text/csv", ["data"],
                       "Gaps between EK80 pings longer than 5 s"),
    "adcp_currents": ("../dataset/adcp/munkholmen_adcp_currents_5min.nc", "application/x-netcdf",
                      ["data"], "ADCP currents, ENU, 5-minute averages"),
    "adcp_echosounder_sv": ("../dataset/adcp/munkholmen_adcp_echosounder_sv.nc",
                            "application/x-netcdf", ["data"], "ADCP echosounder Sv, 70/90/120 kHz"),
    "ctd_1min": ("../dataset/ctd/munkholmen_ctd_1min.csv", "text/csv", ["data"],
                 "CTD, 1-minute means"),
    "ctd_4hz": ("../dataset/ctd/munkholmen_ctd_4hz.csv", "text/csv", ["data"], "CTD, full rate"),
}


def day_item(uri: str, day: str, options: dict, public: str) -> dict:
    """The Item for one day: products/<day>, plus the Sv store from sv/<day>."""
    from oceanstream.stac.echodata import ITEM_FILENAME, build_day_item

    item = build_day_item(
        f"{uri}/products/{day}", COLLECTION_ID, storage_options=options,
        self_href=f"{public}/products/{day}/{ITEM_FILENAME}",
    )
    sv = build_day_item(f"{uri}/sv/{day}", COLLECTION_ID, storage_options=options)
    for key, asset in sv["assets"].items():
        asset["href"] = f"../../sv/{day}/{asset['href'].removeprefix('./')}"
        item["assets"][key] = asset
    props, sv_props = item["properties"], sv["properties"]
    props["start_datetime"] = min(props["start_datetime"], sv_props["start_datetime"])
    props["end_datetime"] = max(props["end_datetime"], sv_props["end_datetime"])
    for key in ("processing:software", "processing:level"):
        if key in sv_props:
            props[key] = sv_props[key]
    item["stac_extensions"] = sorted(set(item["stac_extensions"]) | set(sv["stac_extensions"]))

    item["geometry"] = {"type": "Point", "coordinates": BUOY}
    item["bbox"] = [*BUOY, *BUOY]
    props["oceanstream:position"] = "nominal position of the moored buoy"
    return item


def absolute(doc: dict, url: str) -> dict:
    """A copy of *doc* (published at *url*) with every href made absolute."""
    out = copy.deepcopy(doc)
    for entry in [*out.get("links", []), *out.get("assets", {}).values()]:
        entry["href"] = urljoin(url, entry["href"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, help="Bucket root of the run, e.g. s3://bucket/munkholmen")
    parser.add_argument("--public-base", required=True, help="Public HTTPS URL of --root")
    parser.add_argument("--copy", type=Path, help="Also write the catalogue here, with absolute hrefs")
    args = parser.parse_args()

    from oceanstream.stac.echodata import COLLECTION_FILENAME, ITEM_FILENAME, build_collection, write_json

    fs, root = filesystem(args.root)
    s3 = args.root.startswith("s3://")
    uri = f"s3://{root}" if s3 else root
    options = s3_options() if s3 else {}
    public = args.public_base.rstrip("/")

    days = sorted(p.rsplit("/", 1)[-1] for p in fs.ls(f"{root}/products", detail=False)
                  if DAY_RE.match(p.rsplit("/", 1)[-1]))
    items = []
    for day in days:
        item = day_item(uri, day, options, public)
        write_json(fs, f"{root}/products/{day}/{ITEM_FILENAME}", item)
        print(f"{day}: {len(item['assets'])} assets")
        items.append(item)

    assets = {
        key: {"href": href, "type": kind, "roles": roles, "title": title}
        for key, (href, kind, roles, title) in COLLECTION_ASSETS.items()
    }
    for png in sorted(fs.glob(f"{root}/products/campaign/*.png")):
        name = png.rsplit("/", 1)[-1]
        thumb = name.endswith("--thumb.png")
        assets["campaign_echogram_" + name.removesuffix(".png").replace("--", "_").lower()] = {
            "href": f"./campaign/{name}", "type": "image/png",
            "roles": ["thumbnail"] if thumb else ["visual"],
        }
    collection = build_collection(
        items, COLLECTION_ID, title=TITLE, description=DESCRIPTION, extra_assets=assets,
        self_href=f"{public}/products/{COLLECTION_FILENAME}",
    )
    collection["license"] = "CC0-1.0"
    collection["keywords"] = ["fisheries acoustics", "echosounder", "EK80", "MVBS", "ADCP", "CTD",
                              "Trondheim Fjord", "Munkholmen"]
    collection["links"].append({"rel": "license", "href": "https://creativecommons.org/publicdomain/zero/1.0/",
                                "type": "text/html", "title": "CC0 1.0"})
    write_json(fs, f"{root}/products/{COLLECTION_FILENAME}", collection)
    print(f"collection: {len(items)} items, {len(assets)} assets → {public}/products/{COLLECTION_FILENAME}")

    if args.copy:
        out = args.copy.expanduser()
        coll_url = f"{public}/products/{COLLECTION_FILENAME}"
        out.mkdir(parents=True, exist_ok=True)
        (out / COLLECTION_FILENAME).write_text(json.dumps(absolute(collection, coll_url), indent=2) + "\n")
        for item in items:
            day = item["properties"]["oceanstream:day"]
            (out / day).mkdir(exist_ok=True)
            doc = absolute(item, f"{public}/products/{day}/{ITEM_FILENAME}")
            (out / day / ITEM_FILENAME).write_text(json.dumps(doc, indent=2) + "\n")
        print(f"copy with absolute hrefs → {out}")


if __name__ == "__main__":
    main()
