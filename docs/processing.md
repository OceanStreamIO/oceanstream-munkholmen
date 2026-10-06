# Processing

The products were made with the OceanStream batch pipeline, `scripts/batch_processing/process_from_raw.py` in [oceanstream-cli](https://github.com/OceanStreamIO/oceanstream-cli), driven by `processing/run-munkholmen-apr2026.sh`. The script runs the pipeline in the two steps the OceanStream Denoise Lab uses:

1. **sv** — raw files to EchoData to Sv, one process per day, into the `sv` container. The raw files are read straight from the Azure file share and deleted once converted.
2. **products** — everything from denoising on, reading that Sv and writing into the `products` container: denoising, the seabed mask, pruning, the MVBS, the echograms, and the whole-deployment MVBS.

It then writes the echogram previews and the Zarr chunks the stores would otherwise lack. The pipeline's stages, and what this run does with them:

| Stage | What it does | Here |
|---|---|---|
| 1–2 | Discover the raw files; convert each to EchoData (Zarr), cropped to 100 m | |
| 3 | Combine a day's EchoData | |
| 4 | Compute Sv, add depth, merge the GPS track, bin the range, write the day's Sv store | No GPS merge: the platform is moored |
| 5 | Denoise: impulse noise, attenuated signal, transient noise, background noise | `munkholmen_denoise.toml` |
| 6 | Detect the seabed and mask it and everything below | Leading edge, mask from 0.5 m above |
| 6b | Prune pings that are mostly empty | Pings with 80 % or more missing samples; cross-talk detector off |
| 7–8 | MVBS; NASC | NASC skipped: no track |
| 9 | Echograms of every stage | Three colour maps |
| 10 | PMTiles and COG | Skipped: no track |
| 11 | Whole-deployment MVBS and echograms | |

## Site settings

| Setting | Value | Why |
|---|---|---|
| Range crop | 100 m | The recording range alternated between 100 m and 500 m over a 74 m seabed; the crop makes every file alike and a day fit in memory |
| Sv range bins | 0.107 m requested, 0.106 m in effect: 3 samples at 38 kHz, 12 at 200 kHz, averaged in the linear domain | A full day denoised within 16 GB |
| Sv precision | 32-bit floats | Same |
| Transducer depth | 0 m | The EK80's own range serves as depth |
| Dask chunk | 250 pings | A ping holds 11 175 complex samples in 3 sectors before the crop |
| Water properties | Measured, per day | See below |
| Surface exclusion | 1 m | The first metre below the transducer is left out of the MVBS |
| Sv clip | −10 dB | Samples louder than this after denoising are removed |
| Seabed | Composite detector on 38 kHz, leading edge, mask from 0.5 m above | See below |
| Pruning | Pings with 80 % or more missing samples dropped | |
| Cross-talk detector | Off | Its reference band (800–1200 m) lies far below the seabed |
| MVBS | 0.5 m × 10 s, also written as NetCDF | |
| Echograms | `ocean_r`, `ek500`, `jet`; no combined long- and short-pulse figure | One pulse setting throughout |
| NASC, PMTiles | Skipped | Stationary platform |

## Water properties

echopype computes sound speed and absorption from temperature, salinity, pressure and pH when all four are given, and otherwise keeps the values stored in the raw files, which here were the EK80 software's defaults of 10 °C and 35 PSU. The run passes `--env-params-file` with measured values per day (`metadata/ek80_env_params.json`): the ADCP's daily mean temperature, the CTD's mean salinity over its record on 13 April, a mid-column pressure of 37.4 dbar and a nominal pH of 8.0.

| Day | Temperature (°C) | Salinity (PSU) |
|---|---|---|
| 10 April | 6.944 | 28.769 |
| 11 April | 6.878 | 28.769 |
| 12 April | 6.915 | 28.769 |
| 13 April | 7.126 | 28.769 |
| 14 April | 7.126 (13 April's mean) | 28.769 |

This gives a sound speed of about 1472 m/s. Both measurements are near the surface and are applied to the whole water column. The pH matters: without it echopype keeps the raw file's values without a warning, so the file carries all four.

## Denoising

The four filters of `munkholmen_denoise.toml` run in sequence — impulse noise, attenuated signal, transient noise and background noise (De Robertis and Higginbottom, 2007) — with the reference layers of the Ryan et al. (2015) open-ocean configuration moved inside the 0–70 m water column; the open-ocean defaults put the attenuation reference at 400–500 m and the transient start depth at 200–250 m, below the seabed here.

| Filter | 38 kHz | 200 kHz |
|---|---|---|
| Impulse | 2 m bins, ping lags 1 and 2, threshold 12 dB | Same |
| Attenuation | Reference layer 30–60 m, 50 side pings, threshold 10 dB | Reference layer 20–50 m, 50 side pings, threshold 10 dB |
| Transient | From 20 m down, 5 m bins, 50 pings, threshold 15 dB, 15th percentile | Same |
| Background | 30 samples × 50 pings, SNR threshold 3 dB, noise cap −125 dB | 30 samples × 50 pings, SNR threshold 3 dB, noise cap −85 dB |

The 200 kHz noise cap is high because that channel's noise floor steps between about −102 and −92 dB re 1 W over minutes, and the estimate must be allowed to follow it. In the Denoise Lab this configuration is the preset `munkholmen-fjord`; [The Denoise Lab](denoise-lab.md) shows what each filter removes.

## Seabed

The seabed is detected on the 38 kHz channel with oceanstream's composite detector (a median filter, a per-ping threshold, morphological cleaning and a continuity check), and the line is the **leading edge** of the seabed echo — the sample where the echo starts, which is the seabed surface — smoothed with a running median: `--seabed-line edge`. The mask starts 0.5 m above the line on both channels and removes everything below.

The detector's default pick, the deepest strong sample, lies in the tail of the echo 4–6 m below the surface and moves with the tail's length from ping to ping. The products of 4 October 2026 used it with a 6 m offset, which left the edge of the seabed echo above the mask in 2–13 % of pings depending on the day and spread short excursions into ramps. The products were remade on 5 October with the leading edge; the [report](report.md#44-seabed-detection) has the numbers.

## Scripts

| Script | Does |
|---|---|
| `fetch_from_fileshare.py` | Copies the small raw inputs from the Azure file share: the EK80 `.idx` index files and the ADCP and CTD files. Resumable |
| `process_munkholmen_sensors.py` | Reads the Signature100 `.ad2cp` files and the SBE19plus logs, and writes the ADCP currents and echosounder Sv, the CTD records, and `ek80_env_params.json` |
| `export_ping_gaps.py` | Lists every gap between pings longer than 5 s from the `.idx` files, as an outage (longer than 30 s) or a pause |
| `run-munkholmen-apr2026.sh` | The EK80 run: both steps, with the settings above |
| `munkholmen_denoise.toml` | The denoising configuration |
| `make_thumbnails.py` | A preview of at most 2000 px beside every echogram, as the Denoise Lab viewer expects |
| `fill_empty_chunks.py` | Writes the chunks Zarr skips, so the public stores read without listing rights |
| `submit_to_denoise_lab.py` | Runs the EK80 script on the Denoise Lab's Prefect worker: packs the script, the configuration and the water properties into a bundle, uploads it, and starts the lab's `denoise-lab-batch/batch` deployment. `--products-only` redoes the second step on the Sv already there |
| `package_munkholmen_dataset.py` | Assembles `outputs/` and, with `--standalone`, the deposit, each with a `MANIFEST.csv` |
| `publish_stac.py` | Writes the STAC Items and the Collection into the bucket, and a copy with absolute links into `stac/` |
| `storage.py` | Opens a local directory or an `s3://` prefix, with the endpoint from `AWS_S3_ENDPOINT` |

## Reproducing

The run starts from the raw EK80, ADCP and CTD files, which are not distributed.

```bash
# 1. Python packages
pip install -r requirements.txt

# 2. echopype (OceanStream fork) and oceanstream-cli, next to this repository.
#    The PyPI release of oceanstream is older than this work: use the repository,
#    which has the --seabed-line option (October 2026) the run script needs.
git clone -b oceanstream-integration https://github.com/OceanStreamIO/echopype.git
git clone https://github.com/OceanStreamIO/oceanstream-cli.git oceanstream
pip install -e ./echopype -e ./oceanstream

# 3. The small raw inputs from the file share (the EK80 files are read in step 5)
cd oceanstream-munkholmen/processing
export AZURE_STORAGE_CONNECTION_STRING='…'   # the storage account holding the share
python fetch_from_fileshare.py --share sintef-ek80-oceanlab --dest ~/data/raw/ek80 --include '*.idx'
python fetch_from_fileshare.py --share sintef-ek80-oceanlab --dest ~/data/raw \
    --include 'adcp/*' --include 'ctd/*'

# 4. Sensors first: this writes the water properties the EK80 run reads
python process_munkholmen_sensors.py --adcp-dir ~/data/raw/adcp --ctd-dir ~/data/raw/ctd \
    --out-dir ~/data/munkholmen_2026/sensors
python export_ping_gaps.py --raw-dir ~/data/raw/ek80 --out ~/data/munkholmen_2026/ek80_recording_gaps.csv

# 5. EK80 pipeline, raw files from the share, products to S3
#    (S3 endpoint and keys from AWS_S3_ENDPOINT and AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
RAW_SOURCE=fileshare FILE_SHARE=sintef-ek80-oceanlab \
STORAGE_BACKEND=s3 S3_BUCKET=my-bucket S3_PREFIX=munkholmen \
EXPERIMENT_ROOT=~/data/munkholmen_2026 SV_PARALLEL_DAYS=1 ./run-munkholmen-apr2026.sh

# 6. Package, and publish the STAC catalogue
python package_munkholmen_dataset.py --root ~/data/munkholmen_2026 \
    --products s3://my-bucket/munkholmen/products
python publish_stac.py --root s3://my-bucket/munkholmen \
    --public-base https://my-bucket.<endpoint host>/munkholmen --copy ../stac
```

With the raw files already on disk, run step 5 with `RAW_SOURCE=local RAW_DIR=~/data/raw/ek80`; with `STORAGE_BACKEND=local` the products go under `EXPERIMENT_ROOT` and step 6 needs no `--products`. `RESUME_STAGE=5` re-runs everything from denoising without touching the Sv. Each day in flight needs 10–16 GB of memory and up to 30 GB of scratch, so raise `SV_PARALLEL_DAYS` only on a host sized for it.

The published products were made on the Denoise Lab's Prefect worker instead of step 5: `submit_to_denoise_lab.py` packs the run script, the denoising configuration and the water properties into a bundle, uploads it to the lab's `batch/` area and starts the lab's `denoise-lab-batch/batch` deployment, which runs both steps one day at a time with the worker's pipeline and credentials; `--products-only` redoes the second step alone.

## Environment and footprint

`requirements.txt` pins the Python packages of the run on the lab worker (Python 3.12, image `oceanstream-echodata`), with echopype from the `oceanstream-integration` branch (commit c93006b3) and oceanstream-cli from source: c8032a5 for the run of 4 October 2026, and 3c8b555, which adds `--seabed-line`, for the products rerun of 5 October. xarray 2026.9 and later cannot write the converted EchoData, so the pin stays below it.

| Where | Hardware | Time |
|---|---|---|
| Edge device | NVIDIA Jetson Orin NX, 16 GB, Python 3.12 on aarch64 | About 6 hours for the whole dataset |
| Lab worker, 4 October | Up to 8 CPUs and 64 GB, one day at a time | 6.3 hours for both steps |
| Lab worker, 5 October | Same | 1.8 hours for the products step alone, of which the echograms take 56 minutes |
