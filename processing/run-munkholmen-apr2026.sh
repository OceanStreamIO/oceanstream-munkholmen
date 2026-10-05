#!/usr/bin/env bash
# Munkholmen buoy deployment (SINTEF OceanLab, Trondheim Fjord), 10–14 April 2026.
#
# Processes the EK80 raw files (WBT Mini, ES38-18|200-18CR, 38 + 200 kHz CW,
# complex samples) with the same pipeline as the OceanStream Denoise Lab, in
# its two steps:
#
#   sv        raw → EchoData → Sv, one process per day, into SV_CONTAINER
#   products  denoise → seabed mask → prune → MVBS → echograms → whole-
#             deployment MVBS, reading that Sv, into PRODUCTS_CONTAINER
#
# The products container holds no copy of Sv: the denoised, seabed-masked and
# pruned stores are masks over the Sv store (one flag bit per step, the
# per-ping background noise, the pings pruning kept), and readers in
# oceanstream rebuild the Sv on open. Echograms are drawn in three colour maps
# (ocean_r, ek500, jet), each with a ≤2000 px preview (--thumb.png) as the
# Denoise Lab viewer expects.
#
# Differences from the Saildrone runs:
#   * stationary platform — no GPS merge, no NASC, no PMTiles
#   * a single pulse setting, so no combined long + short pulse echogram
#   * the recording range alternates between 100 m and 500 m over a ~76 m
#     seabed, so every file is cropped to 100 m at conversion
#   * Sv is averaged into ~0.107 m range bins (3 samples at 38 kHz, 12 at
#     200 kHz) so a full day fits in memory on a 16 GB host
#   * sound speed and absorption come from the measured temperature (ADCP)
#     and salinity (CTD) instead of the EK80 settings (10 °C, 35 PSU)
#   * the seabed (the leading edge of its echo) is detected and masked
#     before MVBS
#   * denoise reference layers sit inside the water column
#     (munkholmen_denoise.toml)
#
# Recording gaps (power drops, plus a ~10–18 s pause every minute) need no
# flag: pings keep their true timestamps and MVBS drops empty time bins.
#
# Raw data are read from the Azure file share (RAW_SOURCE=fileshare, needs
# AZURE_STORAGE_CONNECTION_STRING and FILE_SHARE) and deleted once converted,
# or from a local directory (RAW_SOURCE=local, RAW_DIR), which is never
# modified. Products go to S3 (STORAGE_BACKEND=s3, S3_BUCKET, S3_PREFIX; the
# endpoint and keys come from the usual AWS_* variables) or under
# EXPERIMENT_ROOT (STORAGE_BACKEND=local).
#
# Usage:
#   ./run-munkholmen-apr2026.sh                   # both steps, all days
#   RESUME_STAGE=4 ./run-munkholmen-apr2026.sh    # Sv from the combined EchoData
#   RESUME_STAGE=5 ./run-munkholmen-apr2026.sh    # products step only
#   START_DATE=2026-04-12 END_DATE=2026-04-12 ./run-munkholmen-apr2026.sh
set -euo pipefail

exec </dev/null

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# The pipeline itself (process_from_raw.py) lives in the oceanstream-cli
# repository, expected next to this one. See ../README.md for the version.
OCEANSTREAM_REPO="${OCEANSTREAM_REPO:-$SCRIPT_DIR/../../oceanstream}"
[[ -f "$OCEANSTREAM_REPO/scripts/batch_processing/process_from_raw.py" ]] \
  || { echo "oceanstream-cli not found at $OCEANSTREAM_REPO — set OCEANSTREAM_REPO" >&2; exit 1; }
OCEANSTREAM_REPO="$(cd "$OCEANSTREAM_REPO" && pwd)"
cd "$OCEANSTREAM_REPO/scripts/batch_processing"

if [[ -n "${VENV:-}" ]]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi
export PYTHONPATH="$OCEANSTREAM_REPO:${PYTHONPATH:-}"
export PYTHONWARNINGS="ignore"

EXPERIMENT_ROOT="${EXPERIMENT_ROOT:-$HOME/data/munkholmen_2026}"
CRUISE_ID="MUNKHOLMEN_2026"
START_DATE="${START_DATE:-2026-04-10}"
END_DATE="${END_DATE:-2026-04-14}"
RESUME_STAGE="${RESUME_STAGE:-0}"
STOP_AFTER_STAGE="${STOP_AFTER_STAGE:-11}"

# ── where raw data come from ────────────────────────────────────────────
RAW_SOURCE="${RAW_SOURCE:-fileshare}"
RAW_DIR="${RAW_DIR:-$HOME/data/raw/ek80}"
FILE_SHARE="${FILE_SHARE:-}"
FILE_SHARE_PATH="${FILE_SHARE_PATH:-}"
# Downloads land in a per-day directory below this one; the converted
# EchoData sits next to them in echodata_intermediate/.
RAW_CACHE_DIR="${RAW_CACHE_DIR:-$EXPERIMENT_ROOT/raw_cache}"

# ── where products go ───────────────────────────────────────────────────
STORAGE_BACKEND="${STORAGE_BACKEND:-local}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-munkholmen}"
SV_CONTAINER="${SV_CONTAINER:-sv}"
PRODUCTS_CONTAINER="${PRODUCTS_CONTAINER:-products}"
PRESET_KEY="munkholmen"

# ── compute ─────────────────────────────────────────────────────────────
# Days converted at the same time in the sv step. Conversion is sequential
# within a day, so this is the main lever on wall time; each day in flight
# needs 10–16 GB of memory and up to ~30 GB of scratch.
SV_PARALLEL_DAYS="${SV_PARALLEL_DAYS:-1}"
# Keep each day's combined EchoData after its Sv is written, so RESUME_STAGE=4
# can recompute Sv without converting again. 0 frees the scratch space instead.
KEEP_INTERMEDIATE="${KEEP_INTERMEDIATE:-1}"
DASK_WORKERS="${DASK_WORKERS:-2}"
DASK_MEMORY_LIMIT="${DASK_MEMORY_LIMIT:-6GB}"
# 11 175 range samples × 3 sectors of complex data per ping: keep Dask chunks
# small enough for a 16 GB host.
CHUNK_PING_TIME="${CHUNK_PING_TIME:-250}"

# ── site settings ───────────────────────────────────────────────────────
MAX_RANGE_M=100
SV_RANGE_BIN_M=0.107
# Measured water properties (ADCP temperature, CTD salinity) written by
# process_munkholmen_sensors.py; run that first.
ENV_PARAMS_FILE="${ENV_PARAMS_FILE:-$EXPERIMENT_ROOT/sensors/ek80_env_params.json}"
[[ -f "$ENV_PARAMS_FILE" ]] || { echo "Missing $ENV_PARAMS_FILE — run process_munkholmen_sensors.py first" >&2; exit 1; }
# Transducer face depth below the surface (metres).
DEPTH_OFFSET="${DEPTH_OFFSET:-0}"
SURFACE_EXCLUSION_DEPTH="${SURFACE_EXCLUSION_DEPTH:-1}"
# The seabed line is the leading edge of the seabed echo, the seabed surface
# (72.8–74.3 m with the tide), and the mask starts 0.5 m above it so the edge
# of the echo goes too. The detector's default line, the deepest strong
# sample, sits 4–6 m lower in the echo's tail and moves with its length.
SEABED_LINE=edge
SEABED_MASK_OFFSET=0.5
MVBS_RANGE_BIN="0.5m"
MVBS_PING_TIME_BIN="10s"
SV_CLIP_MAX_DB=-10
PRUNE_THRESHOLD=0.8
COLORMAPS="ocean_r,ek500,jet"

LOG_DIR="$EXPERIMENT_ROOT/logs"
mkdir -p "$LOG_DIR"

STORAGE_ARGS=()
case "$STORAGE_BACKEND" in
  s3)
    [[ -n "$S3_BUCKET" ]] || { echo "STORAGE_BACKEND=s3 needs S3_BUCKET" >&2; exit 1; }
    STORAGE_ARGS=(--storage-backend s3 --s3-bucket "$S3_BUCKET" --s3-prefix "$S3_PREFIX")
    ;;
  local)
    STORAGE_ARGS=(--storage-backend local --local-save "$EXPERIMENT_ROOT")
    ;;
  *) echo "STORAGE_BACKEND must be s3 or local" >&2; exit 1 ;;
esac

# Arguments every invocation shares.
COMMON_ARGS=(
  --cruise-id "$CRUISE_ID"
  --waveform-mode CW
  --encode-mode complex
  --expected-categories short_pulse
  --n-workers "$DASK_WORKERS"
  --memory-limit "$DASK_MEMORY_LIMIT"
  --chunk-ping-time "$CHUNK_PING_TIME"
  --parallel-workers 1
  # Each container holds several days, so it is never empty.
  --force
  "${STORAGE_ARGS[@]}"
)

if [[ "$RAW_SOURCE" == "fileshare" ]]; then
  [[ -n "$FILE_SHARE" ]] || { echo "RAW_SOURCE=fileshare needs FILE_SHARE" >&2; exit 1; }
  [[ -n "${AZURE_STORAGE_CONNECTION_STRING:-}" ]] \
    || { echo "RAW_SOURCE=fileshare needs AZURE_STORAGE_CONNECTION_STRING" >&2; exit 1; }
  # An empty --file-share-path is the share's root.
  RAW_ARGS=(--raw-source fileshare --file-share "$FILE_SHARE" --file-share-path "$FILE_SHARE_PATH")
else
  RAW_ARGS=(--raw-source local --raw-dir "$RAW_DIR")
fi

INTERMEDIATE_ARGS=()
if [[ "$KEEP_INTERMEDIATE" == "1" ]]; then
  INTERMEDIATE_ARGS=(--keep-intermediate)
fi

# ── step 1: Sv, one process per day ─────────────────────────────────────
sv_day() {
  local day="$1"
  python -u process_from_raw.py \
    "${COMMON_ARGS[@]}" \
    "${RAW_ARGS[@]}" \
    --raw-cache-dir "$RAW_CACHE_DIR/$day" \
    --output-container "$SV_CONTAINER" \
    --start-date "$day" \
    --end-date "$day" \
    --max-range-m "$MAX_RANGE_M" \
    --sv-range-bin-m "$SV_RANGE_BIN_M" \
    --depth-offset "$DEPTH_OFFSET" \
    --env-params-file "$ENV_PARAMS_FILE" \
    --reuse-converted \
    "${INTERMEDIATE_ARGS[@]}" \
    --sv-float32 \
    --resume-stage "$RESUME_STAGE" \
    --stop-after-stage 4 \
    >>"$LOG_DIR/sv-$day.log" 2>&1
}

days_in_range() {
  python - "$START_DATE" "$END_DATE" <<'EOF'
import sys
from datetime import date, timedelta
day, end = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])
while day <= end:
    print(day.isoformat())
    day += timedelta(days=1)
EOF
}

if (( RESUME_STAGE < 5 )); then
  echo "sv: $START_DATE → $END_DATE, $SV_PARALLEL_DAYS day(s) at a time, logs in $LOG_DIR"
  failed=0
  running=0
  for day in $(days_in_range); do
    if (( running >= SV_PARALLEL_DAYS )); then
      wait -n || failed=1
      running=$((running - 1))
    fi
    echo "  sv $day"
    sv_day "$day" &
    running=$((running + 1))
  done
  while (( running > 0 )); do
    wait -n || failed=1
    running=$((running - 1))
  done
  (( failed == 0 )) || { echo "sv step failed — see $LOG_DIR/sv-*.log" >&2; exit 1; }
fi

(( STOP_AFTER_STAGE >= 5 )) || exit 0

# ── step 2: denoise onwards, reading the Sv ─────────────────────────────
echo "products: $START_DATE → $END_DATE, log in $LOG_DIR/products.log"
python -u process_from_raw.py \
  "${COMMON_ARGS[@]}" \
  --raw-cache-dir "$RAW_CACHE_DIR/products" \
  --output-container "$PRODUCTS_CONTAINER" \
  --sv-source-container "$SV_CONTAINER" \
  --start-date "$START_DATE" \
  --end-date "$END_DATE" \
  --depth-offset "$DEPTH_OFFSET" \
  --resume-stage "$(( RESUME_STAGE > 5 ? RESUME_STAGE : 5 ))" \
  --stop-after-stage "$STOP_AFTER_STAGE" \
  --denoise-config "$SCRIPT_DIR/munkholmen_denoise.toml" \
  --preset-key "$PRESET_KEY" \
  --surface-exclusion-depth "$SURFACE_EXCLUSION_DEPTH" \
  --sv-clip-max-db "$SV_CLIP_MAX_DB" \
  --seabed-mask \
  --seabed-mask-offset "$SEABED_MASK_OFFSET" \
  --seabed-line "$SEABED_LINE" \
  --prune-threshold "$PRUNE_THRESHOLD" \
  --no-crosstalk \
  --mvbs-range-bin "$MVBS_RANGE_BIN" \
  --mvbs-ping-time-bin "$MVBS_PING_TIME_BIN" \
  --save-mvbs-netcdf \
  --colormaps "$COLORMAPS" \
  --skip-nasc \
  --skip-pmtiles \
  --skip-combined-echograms \
  >>"$LOG_DIR/products.log" 2>&1

# ── step 3: echogram previews, as the Denoise Lab viewer writes them ────
if [[ "$STORAGE_BACKEND" == "s3" ]]; then
  PRODUCTS_ROOT="s3://$S3_BUCKET/$S3_PREFIX/$PRODUCTS_CONTAINER"
else
  PRODUCTS_ROOT="$EXPERIMENT_ROOT/$PRODUCTS_CONTAINER"
fi
python -u "$SCRIPT_DIR/make_thumbnails.py" "$PRODUCTS_ROOT" >>"$LOG_DIR/products.log" 2>&1

# ── step 4: write the chunks Zarr skips, so public readers get no 403 ──
python -u "$SCRIPT_DIR/fill_empty_chunks.py" "$PRODUCTS_ROOT" "${PRODUCTS_ROOT%/*}/$SV_CONTAINER" \
  >>"$LOG_DIR/products.log" 2>&1
echo "done: products in $PRODUCTS_ROOT"
