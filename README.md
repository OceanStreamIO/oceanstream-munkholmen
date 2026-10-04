# OceanStream at Munkholmen, April 2026

Processing code, configuration and data products for the echosounder deployment on the SINTEF OceanLab Munkholmen buoy in Trondheim Fjord, 10–14 April 2026.

A Simrad EK80 WBT Mini (38 and 200 kHz) pinged from the buoy's moonpool for 3.5 days while the buoy's own Nortek Signature100 ADCP and Sea-Bird SBE19plus CTD recorded currents and water properties. The raw echosounder data were processed on the edge device that collected them, an NVIDIA Jetson Orin NX with 16 GB of memory, using [echopype](https://github.com/OSOceanAcoustics/echopype) and the [OceanStream](https://github.com/OceanStreamIO/oceanstream-cli) batch pipeline.

## Contents

| Path | What it holds |
|---|---|
| `outputs/` | The small data products, and `MANIFEST.csv` with checksums for every product file |
| `processing/` | The scripts and configuration that produced them |
| `metadata/` | The dataset description, the dataset record metadata, and the water properties used for calibration |
| `requirements.txt` | Package versions used for the run |

The EK80 MVBS stores, the ADCP echosounder Sv and the full-rate CTD record (137 MB) are distributed with the published dataset, not in this repository; `processing/package_munkholmen_dataset.py` rebuilds them from the raw data, and `outputs/MANIFEST.csv` lists their checksums. The raw EK80 files (124 GB) and the full-resolution Sv are not distributed.

## Data products

`metadata/dataset_README.md` is the full description: variables, units, file formats, processing steps, recording gaps and known limitations. Read it before using the data. Files marked † are in the published dataset only.

| Product | File |
|---|---|
| EK80 MVBS, whole deployment (10 s × 0.5 m cells) | `outputs/ek80/campaign/campaign_mvbs_short_pulse.nc` and `.zarr.zip` † |
| EK80 MVBS, one store per day | `outputs/ek80/YYYY-MM-DD/*--mvbs.zarr.zip` † |
| Gaps between pings longer than 5 s | `outputs/ek80/ek80_recording_gaps.csv` |
| ADCP currents, ENU, 5-minute averages | `outputs/adcp/munkholmen_adcp_currents_5min.nc` |
| ADCP echosounder Sv at 70, 90 and 120 kHz | `outputs/adcp/munkholmen_adcp_echosounder_sv.nc` † |
| CTD, 1-minute means | `outputs/ctd/munkholmen_ctd_1min.csv` |
| CTD, full rate | `outputs/ctd/munkholmen_ctd_4hz.csv` † |

```python
import xarray as xr

# from the published dataset, or after running the processing
mvbs = xr.open_dataset("outputs/ek80/campaign/campaign_mvbs_short_pulse.nc")
sv_38 = mvbs["Sv"].isel(channel=0)   # channel 1 is 200 kHz
```

Three things to know before interpreting the data:

- The 200 kHz channel is dominated by noise below about 10 m.
- The band at 15–35 m between 12:10 and 15:38 on 10 April (38 kHz) is consistent with a false bottom caused by the fast ping rate used during those hours, not biology.
- The echosounder was not calibrated with a reference sphere; Sv uses the factory gains stored in the raw files.

## Processing

| Step | Script |
|---|---|
| ADCP and CTD products, and the water properties for the EK80 calibration | `processing/process_munkholmen_sensors.py` |
| Table of recording gaps, read from the EK80 `.idx` files | `processing/export_ping_gaps.py` |
| EK80: raw → Sv → denoise → seabed mask → MVBS → echograms | `processing/run-munkholmen-apr2026.sh` with `processing/munkholmen_denoise.toml` |
| Assemble `outputs/` | `processing/package_munkholmen_dataset.py` |

The EK80 run script is a thin wrapper: it calls `process_from_raw.py` from the oceanstream-cli repository with the settings for this site. What differs from an open-ocean survey run:

- every file is cropped to 100 m range (the recording range alternated between 100 m and 500 m over a 74 m seabed);
- sound speed and absorption come from the measured temperature (ADCP) and salinity (CTD), not the values entered in the EK80 software;
- Sv is averaged into 0.106 m range bins and stored as 32-bit floats, so that a full day can be denoised in 16 GB of memory;
- the denoise reference layers sit inside the 74 m water column;
- the seabed is detected and masked;
- no GPS merge and no NASC, because the platform is stationary.

## Reproducing

The run starts from the raw EK80, ADCP and CTD files, which are not part of this repository.

```bash
# 1. Python packages
pip install -r requirements.txt

# 2. echopype (OceanStream fork) and oceanstream-cli, next to this repository
git clone -b oceanstream-integration https://github.com/OceanStreamIO/echopype.git
git clone https://github.com/OceanStreamIO/oceanstream-cli.git oceanstream
pip install -e ./echopype -e ./oceanstream

# 3. Sensors first: this writes the water properties the EK80 run reads
cd oceanstream-munkholmen/processing
python process_munkholmen_sensors.py --adcp-dir ~/data/raw/adcp --ctd-dir ~/data/raw/ctd \
    --out-dir ~/data/munkholmen_2026/sensors
python export_ping_gaps.py --raw-dir ~/data/raw/ek80 --out ~/data/munkholmen_2026/ek80_recording_gaps.csv

# 4. EK80 pipeline (about 6 hours on the Jetson; resumable with RESUME_STAGE)
RAW_DIR=~/data/raw/ek80 EXPERIMENT_ROOT=~/data/munkholmen_2026 ./run-munkholmen-apr2026.sh

# 5. Package
python package_munkholmen_dataset.py --root ~/data/munkholmen_2026
```

## Licence and credits

The code is released under the MIT licence (see `LICENSE`). The data products in `outputs/` are released under CC0 1.0.

Funded by Akershus fylkeskommune (AFK) through the project *Digital Solutions for Automated Monitoring of Seaweed Farm Operations*, with SINTEF Ocean as R&D partner. The EK80 WBT Mini was loaned by NTNU. Built on [echopype](https://github.com/OSOceanAcoustics/echopype).
