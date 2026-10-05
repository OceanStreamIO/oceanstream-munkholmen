# OceanStream at Munkholmen, April 2026

Processing code, configuration and data products for the echosounder deployment on the SINTEF OceanLab Munkholmen buoy in Trondheim Fjord, 10–14 April 2026.

A Simrad EK80 WBT Mini (38 and 200 kHz) pinged from the buoy's moonpool for 3.5 days while the buoy's own Nortek Signature100 ADCP and Sea-Bird SBE19plus CTD recorded currents and water properties. The raw echosounder data were first processed on the edge device that collected them, an NVIDIA Jetson Orin NX with 16 GB of memory, using [echopype](https://github.com/OSOceanAcoustics/echopype) and the [OceanStream](https://github.com/OceanStreamIO/oceanstream-cli) batch pipeline. The products here come from a second run of the same pipeline on the Prefect worker of the OceanStream Denoise Lab, on the [EDITO DataLab](https://datalab.dive.edito.eu), made the way the lab runs it: reading the raw files from the Azure file share they were uploaded to, and writing every product to object storage.

## Contents

| Path | What it holds |
|---|---|
| `outputs/` | The small data products, and `MANIFEST.csv` with checksums for every product file |
| `processing/` | The scripts and configuration that produced them |
| `metadata/` | The dataset description, the dataset record metadata, and the water properties used for calibration |
| `stac/` | The STAC catalogue of the products in the bucket, with absolute links so it opens from a clone |
| `requirements.txt` | Package versions used for the run |

The EK80 MVBS stores, the ADCP echosounder Sv and the full-rate CTD record are not in this repository; they are in the public bucket described below, and `outputs/MANIFEST.csv` lists their checksums. The raw EK80 files (124 GB) are not distributed.

## Where the data are

Everything the run produced is in a public S3 bucket at CloudFerro (Warsaw), readable without credentials:

`s3://oceanstream-bucket/munkholmen/` — endpoint `https://s3.waw3-1.cloudferro.com`, or over HTTPS at `https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen/`

| Prefix | What it holds |
|---|---|
| `dataset/` | The packaged dataset: everything in `outputs/` plus the files marked † below, the dataset README, the processing files and `MANIFEST.csv` |
| `sv/YYYY-MM-DD/` | Sv at the full ping rate in 0.106 m range bins, one Zarr store per day |
| `products/YYYY-MM-DD/` | The denoised, seabed-masked and pruned Sv, the MVBS (Zarr and NetCDF), and echograms of each stage |
| `products/MUNKHOLMEN_2026/` | The whole-deployment MVBS (Zarr) |
| `products/campaign/` | The whole-deployment echograms |
| `products/collection.json` | The STAC Collection: one Item per day (`products/YYYY-MM-DD/item.json`) listing that day's stores, NetCDF files and echograms, and the whole-deployment and dataset files as Collection assets |

The STAC catalogue starts at `https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen/products/collection.json`; any STAC client or [STAC Browser](https://radiantearth.github.io/stac-browser/) can open it. `stac/` in this repository holds the same documents with every link absolute.

The denoised, seabed-masked and pruned stores do not repeat the Sv. They hold what each step removed — one flag bit per filter, the background noise level of every ping, and the pings that pruning kept — and oceanstream rebuilds the Sv from them and the `sv/` store when they are opened (see "Reading the data").

## Data products

`metadata/dataset_README.md` is the full description: variables, units, file formats, processing steps, recording gaps and known limitations. Read it before using the data. Files marked † are in the bucket and the published dataset only.

| Product | File |
|---|---|
| EK80 MVBS, whole deployment (10 s × 0.5 m cells) | `outputs/ek80/campaign/campaign_mvbs_short_pulse.nc` and `.zarr.zip` † |
| EK80 MVBS, one per day | `outputs/ek80/YYYY-MM-DD/*--mvbs.nc` and `.zarr.zip` † |
| EK80 MVBS echograms, per day and whole deployment | `outputs/ek80/*/echograms/*.png` † |
| Gaps between pings longer than 5 s | `outputs/ek80/ek80_recording_gaps.csv` |
| ADCP currents, ENU, 5-minute averages | `outputs/adcp/munkholmen_adcp_currents_5min.nc` |
| ADCP echosounder Sv at 70, 90 and 120 kHz | `outputs/adcp/munkholmen_adcp_echosounder_sv.nc` † |
| CTD, 1-minute means | `outputs/ctd/munkholmen_ctd_1min.csv` |
| CTD, full rate | `outputs/ctd/munkholmen_ctd_4hz.csv` † |
| EK80 Sv, full ping rate, and the denoising masks | bucket `sv/` and `products/` |
| EK80 echograms of the Sv, denoised, pruned and MVBS data, in three colour maps | bucket `products/YYYY-MM-DD/{raw,denoised,pruned,mvbs}/` |

### Reading the data

```python
import xarray as xr

# from outputs/ after packaging, or from the bucket's dataset/ folder
mvbs = xr.open_dataset("outputs/ek80/campaign/campaign_mvbs_short_pulse.nc")
sv_38 = mvbs["Sv"].isel(channel=0)   # channel 1 is 200 kHz

# straight from the bucket, without credentials
import s3fs
import zarr

fs = s3fs.S3FileSystem(anon=True, endpoint_url="https://s3.waw3-1.cloudferro.com", asynchronous=True)

def open_public(uri):
    # Zarr does not write chunks that hold only the fill value. The bucket
    # answers an anonymous request for one of those with 403, not 404, so
    # read a 403 as "empty" too.
    store = zarr.storage.FsspecStore(fs, path=uri.removeprefix("s3://"), read_only=True,
                                     allowed_exceptions=(FileNotFoundError, PermissionError))
    return xr.open_zarr(store, zarr_format=3)

day = "s3://oceanstream-bucket/munkholmen/products/2026-04-12"
mvbs_day = open_public(f"{day}/2026-04-12--short_pulse--mvbs.zarr")

# the pruned Sv, rebuilt from its masks and the sv/ store (needs oceanstream)
from oceanstream.echodata.products import resolve_at
pruned = f"{day}/2026-04-12--short_pulse--pruned.zarr"
sv = resolve_at(open_public(pruned), pruned, open_public)
```

The `dataset/` folder holds plain files (NetCDF, zipped Zarr, CSV, PNG) that download over HTTPS, e.g. `https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen/dataset/MANIFEST.csv`, or all at once with `aws s3 sync --no-sign-request --endpoint-url https://s3.waw3-1.cloudferro.com --region us-east-1 s3://oceanstream-bucket/munkholmen/dataset/ .` (any region works; the CLI just needs one).

Three things to know before interpreting the data:

- The 200 kHz channel is dominated by noise below about 10 m.
- The band at 15–35 m between 12:10 and 15:38 on 10 April (38 kHz) is consistent with a false bottom caused by the fast ping rate used during those hours, not biology.
- The echosounder was not calibrated with a reference sphere; Sv uses the factory gains stored in the raw files.

## Processing

| Step | Script |
|---|---|
| Copy the ADCP, CTD and EK80 index files from the Azure file share | `processing/fetch_from_fileshare.py` |
| ADCP and CTD products, and the water properties for the EK80 calibration | `processing/process_munkholmen_sensors.py` |
| Table of recording gaps, read from the EK80 `.idx` files | `processing/export_ping_gaps.py` |
| EK80: raw → Sv, then denoise → seabed mask → prune → MVBS → echograms → whole-deployment MVBS | `processing/run-munkholmen-apr2026.sh` with `processing/munkholmen_denoise.toml` |
| Echogram previews (≤2000 px), run by the script above | `processing/make_thumbnails.py` |
| Run the EK80 script on the Denoise Lab's Prefect worker | `processing/submit_to_denoise_lab.py` |
| Assemble `outputs/` and the dataset | `processing/package_munkholmen_dataset.py` |
| STAC catalogue, in the bucket and in `stac/` | `processing/publish_stac.py` |

The EK80 run script is a thin wrapper around `process_from_raw.py` from the oceanstream-cli repository. It runs it in the two steps the OceanStream Denoise Lab uses: first the Sv of each day, one process per day, into the `sv` container; then everything from denoising on, which reads that Sv and writes into the `products` container. Raw files are read straight from the file share and deleted once converted. What differs from an open-ocean survey run:

- every file is cropped to 100 m range (the recording range alternated between 100 m and 500 m over a 74 m seabed);
- sound speed and absorption come from the measured temperature (ADCP) and salinity (CTD), not the values entered in the EK80 software;
- Sv is averaged into 0.106 m range bins and stored as 32-bit floats, so that a full day can be denoised in 16 GB of memory;
- the denoise reference layers sit inside the 74 m water column;
- the seabed is detected and masked;
- no GPS merge, no NASC and no map tiles, because the platform is stationary;
- one pulse setting throughout, so there is no combined long- and short-pulse echogram.

The same days are also set up in the OceanStream Denoise Lab, as the survey `munkholmen-2026` with the preset `munkholmen-fjord` (this repository's `munkholmen_denoise.toml`), for trying other denoising parameters on the most representative day, 12 April.

## Reproducing

The run starts from the raw EK80, ADCP and CTD files, which are not part of this repository.

```bash
# 1. Python packages
pip install -r requirements.txt

# 2. echopype (OceanStream fork) and oceanstream-cli, next to this repository
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

The published products were made on the Denoise Lab's Prefect worker instead of step 5: `submit_to_denoise_lab.py` packs the run script, the denoise configuration and the water properties into a bundle, uploads it to the lab's `batch/` area and starts the lab's `denoise-lab-batch/batch` deployment, which runs both steps one day at a time with the worker's pipeline and credentials. That run took 6.3 hours, one day at a time on 8 CPUs; the one on the Jetson about 6 hours.

## Licence and credits

The code is released under the MIT licence (see `LICENSE`). The data products in `outputs/` and in the bucket are released under CC0 1.0.

Funded by Akershus fylkeskommune (AFK) through the project *Digital Solutions for Automated Monitoring of Seaweed Farm Operations*, with SINTEF Ocean as R&D partner. The EK80 WBT Mini was loaned by NTNU. Built on [echopype](https://github.com/OSOceanAcoustics/echopype).
