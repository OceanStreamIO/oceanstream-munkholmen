#!/usr/bin/env python
"""Run the EK80 processing on the OceanStream Denoise Lab worker.

The lab's Prefect worker runs on a large-memory node, with the pipeline
installed at /opt/oceanstream and the Azure and S3 credentials in its
environment. This packs what ``run-munkholmen-apr2026.sh`` needs — the
processing files and the water properties written by
``process_munkholmen_sensors.py`` — into a bundle, puts it in the lab's
``batch/`` area, and starts the lab's ``denoise-lab-batch/batch`` deployment
with the two steps of the run: Sv one day at a time, then the products.

The S3 endpoint and keys come from ``AWS_S3_ENDPOINT`` and the usual
``AWS_*`` variables, the Prefect API from ``PREFECT_API_URL``.

Usage:
  python submit_to_denoise_lab.py --bucket my-bucket \\
      --env-params ~/data/munkholmen_2026/sensors/ek80_env_params.json
  # add --products-only to redo denoising onwards on the Sv already there
"""

from __future__ import annotations

import argparse
import io
import json
import os
import tarfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from storage import filesystem

SCRIPT_DIR = Path(__file__).resolve().parent
BUNDLE_FILES = (
    "run-munkholmen-apr2026.sh",
    "munkholmen_denoise.toml",
    "make_thumbnails.py",
    "fill_empty_chunks.py",
    "storage.py",
)
FLOW, DEPLOYMENT = "denoise-lab-batch", "batch"

# Both steps of the run script, from inside the unpacked bundle. Sv first
# with small Dask workers, then the products, which hold a day in memory.
COMMAND = """\
set -euo pipefail
export EXPERIMENT_ROOT="$PWD" ENV_PARAMS_FILE="$PWD/sensors/ek80_env_params.json"
STOP_AFTER_STAGE=4 DASK_MEMORY_LIMIT="$SV_MEMORY" bash processing/run-munkholmen-apr2026.sh
RESUME_STAGE=5 DASK_MEMORY_LIMIT="$PRODUCTS_MEMORY" bash processing/run-munkholmen-apr2026.sh
"""
# The products step alone, on the Sv already in S3.
PRODUCTS_COMMAND = "\n".join(
    line for line in COMMAND.splitlines() if not line.startswith("STOP_AFTER_STAGE=4")
) + "\n"


def build_bundle(env_params: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name in BUNDLE_FILES:
            tar.add(SCRIPT_DIR / name, arcname=f"processing/{name}")
        tar.add(env_params, arcname="sensors/ek80_env_params.json")
    return buffer.getvalue()


def _api(url: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True, help="S3 bucket of the lab and of the products")
    parser.add_argument("--env-params", type=Path, required=True,
                        help="ek80_env_params.json from process_munkholmen_sensors.py")
    parser.add_argument("--lab-prefix", default="denoise-lab", help="The lab's S3 prefix")
    parser.add_argument("--products-prefix", default="munkholmen", help="Where the products go")
    parser.add_argument("--file-share", default="sintef-ek80-oceanlab")
    parser.add_argument("--raw-cache-dir", default="/data/cache/raw/munkholmen",
                        help="Scratch for downloads and EchoData, on the worker")
    parser.add_argument("--start-date", default="2026-04-10")
    parser.add_argument("--end-date", default="2026-04-14")
    parser.add_argument("--sv-parallel-days", type=int, default=1)
    parser.add_argument("--dask-workers", type=int, default=2)
    parser.add_argument("--sv-memory", default="8GB", help="Per Dask worker, Sv step")
    parser.add_argument("--products-memory", default="12GB", help="Per Dask worker, products step")
    parser.add_argument("--prefect-api", default=os.environ.get("PREFECT_API_URL", ""))
    parser.add_argument("--products-only", action="store_true",
                        help="Rerun only the products step, reading the Sv already in S3")
    parser.add_argument("--dry-run", action="store_true", help="Build the bundle, print the run, submit nothing")
    args = parser.parse_args()

    if not args.prefect_api and not args.dry_run:
        parser.error("Set PREFECT_API_URL or pass --prefect-api")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"munkholmen-{stamp}.tar.gz"
    bundle = build_bundle(args.env_params.expanduser())
    env = {
        "OCEANSTREAM_REPO": "/opt/oceanstream",
        "VENV": "/opt/venv",
        "RAW_SOURCE": "fileshare",
        "FILE_SHARE": args.file_share,
        "FILE_SHARE_PATH": "",
        "RAW_CACHE_DIR": args.raw_cache_dir,
        "STORAGE_BACKEND": "s3",
        "S3_BUCKET": args.bucket,
        "S3_PREFIX": args.products_prefix,
        "START_DATE": args.start_date,
        "END_DATE": args.end_date,
        "SV_PARALLEL_DAYS": str(args.sv_parallel_days),
        # The worker's scratch volume holds one day's EchoData at a time.
        "KEEP_INTERMEDIATE": "0",
        "DASK_WORKERS": str(args.dask_workers),
        "SV_MEMORY": args.sv_memory,
        "PRODUCTS_MEMORY": args.products_memory,
    }
    command = PRODUCTS_COMMAND if args.products_only else COMMAND
    parameters = {"bundle": name, "command": ["bash", "-c", command], "env": env}
    if args.dry_run:
        print(f"bundle {name}: {len(bundle)} bytes")
        print(json.dumps(parameters, indent=2))
        return

    fs, root = filesystem(f"s3://{args.bucket}/{args.lab_prefix}/batch")
    with fs.open(f"{root}/{name}", "wb") as fh:
        fh.write(bundle)
    print(f"uploaded s3://{root}/{name}")

    api = args.prefect_api.rstrip("/")
    deployment = _api(f"{api}/deployments/name/{FLOW}/{DEPLOYMENT}")
    run = _api(f"{api}/deployments/{deployment['id']}/create_flow_run",
               {"parameters": parameters, "name": f"munkholmen-{stamp}"})
    print(f"flow run {run['name']} ({run['id']}) submitted to {FLOW}/{DEPLOYMENT}")


if __name__ == "__main__":
    main()
