#!/usr/bin/env bash
# Munkholmen buoy deployment (SINTEF OceanLab, Trondheim Fjord), 10–14 April 2026.
#
# Processes the EK80 raw files (WBT Mini, ES38-18|200-18CR, 38 + 200 kHz CW,
# complex samples) from a local directory into per-day Sv, denoised Sv, MVBS
# and echograms. Fully local: no Azure credentials are sourced.
#
# Differences from the Saildrone runs:
#   * stationary platform — no GPS merge, no NASC, no PMTiles
#   * the recording range alternates between 100 m and 500 m over a ~76 m
#     seabed, so every file is cropped to 100 m at conversion
#   * Sv is averaged into ~0.107 m range bins (3 samples at 38 kHz, 12 at
#     200 kHz) so a full day fits in memory on a 16 GB host
#   * sound speed and absorption come from the measured temperature (ADCP)
#     and salinity (CTD) instead of the EK80 settings (10 °C, 35 PSU)
#   * the seabed is detected and masked before MVBS
#   * denoise reference layers sit inside the water column
#     (munkholmen_denoise.toml)
#
# Recording gaps (power drops, plus a ~10–18 s pause every minute) need no
# flag: pings keep their true timestamps and MVBS drops empty time bins.
#
# Usage:
#   ./run-munkholmen-apr2026.sh                 # full run, all days
#   RESUME_STAGE=4 ./run-munkholmen-apr2026.sh  # Sv from the combined EchoData
#   RESUME_STAGE=5 ./run-munkholmen-apr2026.sh  # re-run from denoise
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

RAW_DIR="${RAW_DIR:-$HOME/data/raw/ek80}"
EXPERIMENT_ROOT="${EXPERIMENT_ROOT:-$HOME/data/munkholmen_2026}"
OUTPUT_CONTAINER="${OUTPUT_CONTAINER:-ek80}"
CRUISE_ID="MUNKHOLMEN_2026"
START_DATE="${START_DATE:-2026-04-10}"
END_DATE="${END_DATE:-2026-04-14}"
RESUME_STAGE="${RESUME_STAGE:-0}"
STOP_AFTER_STAGE="${STOP_AFTER_STAGE:-11}"

# 11 175 range samples × 3 sectors of complex data per ping: keep Dask chunks
# small enough for a 16 GB host.
CHUNK_PING_TIME="${CHUNK_PING_TIME:-250}"
MAX_RANGE_M=100
SV_RANGE_BIN_M=0.107
# Measured water properties (ADCP temperature, CTD salinity) written by
# process_munkholmen_sensors.py; run that first.
ENV_PARAMS_FILE="${ENV_PARAMS_FILE:-$EXPERIMENT_ROOT/sensors/ek80_env_params.json}"
[[ -f "$ENV_PARAMS_FILE" ]] || { echo "Missing $ENV_PARAMS_FILE — run process_munkholmen_sensors.py first" >&2; exit 1; }
# Transducer face depth below the surface (metres).
DEPTH_OFFSET="${DEPTH_OFFSET:-0}"
SURFACE_EXCLUSION_DEPTH="${SURFACE_EXCLUSION_DEPTH:-1}"
# The composite detector settles ~4–5 m below the onset of the seabed echo
# (74.7 m); start the mask 6 m above the detection, ~1 m above the onset.
SEABED_MASK_OFFSET=6
MVBS_RANGE_BIN="0.5m"
MVBS_PING_TIME_BIN="10s"
SV_CLIP_MAX_DB=-10

LOG_FILE="$EXPERIMENT_ROOT/$OUTPUT_CONTAINER-run.log"
mkdir -p "$EXPERIMENT_ROOT"

FORCE_ARGS=()
if [[ "$RESUME_STAGE" != "0" ]]; then
  FORCE_ARGS=(--force)
fi

python -u process_from_raw.py \
  --cruise-id "$CRUISE_ID" \
  --raw-source local \
  --raw-dir "$RAW_DIR" \
  --storage-backend local \
  --local-save "$EXPERIMENT_ROOT" \
  --output-container "$OUTPUT_CONTAINER" \
  --start-date "$START_DATE" \
  --end-date "$END_DATE" \
  --waveform-mode CW \
  --encode-mode complex \
  --max-range-m "$MAX_RANGE_M" \
  --sv-range-bin-m "$SV_RANGE_BIN_M" \
  --depth-offset "$DEPTH_OFFSET" \
  --env-params-file "$ENV_PARAMS_FILE" \
  --reuse-converted \
  --keep-intermediate \
  --sv-float32 \
  --chunk-ping-time "$CHUNK_PING_TIME" \
  --surface-exclusion-depth "$SURFACE_EXCLUSION_DEPTH" \
  --denoise-config "$SCRIPT_DIR/munkholmen_denoise.toml" \
  --sv-clip-max-db "$SV_CLIP_MAX_DB" \
  --seabed-mask \
  --seabed-mask-offset "$SEABED_MASK_OFFSET" \
  --no-crosstalk \
  --mvbs-range-bin "$MVBS_RANGE_BIN" \
  --mvbs-ping-time-bin "$MVBS_PING_TIME_BIN" \
  --expected-categories short_pulse \
  --parallel-workers 1 \
  --skip-nasc \
  --skip-pmtiles \
  --skip-combined-echograms \
  --mvbs-echograms-only \
  --resume-stage "$RESUME_STAGE" \
  --stop-after-stage "$STOP_AFTER_STAGE" \
  "${FORCE_ARGS[@]}" \
  2>&1 | tee -a "$LOG_FILE"
