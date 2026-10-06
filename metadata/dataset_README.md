# OceanStream Edge deployment at Munkholmen Ocean Observatory – EK80, ADCP and CTD, Trondheim Fjord, 10–14 April 2026

Mean volume backscattering strength (MVBS) from a Simrad EK80 echosounder deployed for 3.5 days on the SINTEF OceanLab Munkholmen buoy in Trondheim Fjord, Norway, with the currents, echosounder backscatter and near-surface water properties recorded by the buoy's own ADCP and CTD over the same period.

| | |
|---|---|
| Site | SINTEF OceanLab Munkholmen buoy, 63° 27.45' N, 010° 22.33' E |
| Period | 2026-04-10 11:29 UTC to 2026-04-14 00:25 UTC |
| Water depth | about 74 m below the transducer |
| Authors | _to be completed_ |
| Licence | CC0 1.0 |
| Funding | Akershus fylkeskommune (AFK), project "Digital Solutions for Automated Monitoring of Seaweed Farm Operations" (Pine View Software AS, with SINTEF Ocean AS as R&D supplier) |

All times are UTC.

## Instruments

| Instrument | Details |
|---|---|
| Echosounder | Simrad EK80 (software 25.2.3.0), WBT Mini 274022, transducer ES38-18\|200-18CR (serial 266) in the buoy moonpool, looking down. Transducer depth taken as 0 m. |
| 38 kHz channel | Split-beam (3 sectors), CW, 1.024 ms pulse, 500 W |
| 200 kHz channel | Single-beam, CW, 0.256 ms pulse, 200 W |
| ADCP | Nortek Signature100 (serial 103128), looking down from about 2.2 m depth; 15 cells of 5 m; echosounder at 70, 90 and 120 kHz |
| CTD | Sea-Bird SBE19plus (serial 01908154) at about 1.1 dbar, with SBE63 oxygen sensor |

The echosounder was not calibrated with a reference sphere. Sv uses the gain and beam parameters stored in the raw files (factory values).

## Contents

```
ek80/
  campaign/campaign_mvbs_short_pulse.nc         whole deployment, NetCDF
  campaign/campaign_mvbs_short_pulse.zarr.zip   whole deployment, zipped Zarr
  campaign/echograms/*.png                      whole-deployment echograms
  YYYY-MM-DD/*--mvbs.nc                         one file per day, NetCDF
  YYYY-MM-DD/*--mvbs.zarr.zip                   one store per day, zipped Zarr
  YYYY-MM-DD/echograms/*.png                    per-day echograms, three colour maps
  ek80_recording_gaps.csv                       every gap between pings longer than 5 s
adcp/
  munkholmen_adcp_currents_5min.nc              currents, ENU, 5-minute averages
  munkholmen_adcp_echosounder_sv.nc             Sv at 70, 90 and 120 kHz
ctd/
  munkholmen_ctd_4hz.csv                        full-rate record
  munkholmen_ctd_1min.csv                       1-minute means
processing/                                     run script and configuration
MANIFEST.csv                                    file list with sizes and SHA-256
```

The raw EK80 files (124 GB) are not distributed. The full-resolution Sv, the denoising masks and the echograms of every processing stage are not part of this deposit; they are in the public bucket `s3://oceanstream-bucket/munkholmen/` (endpoint `https://s3.waw3-1.cloudferro.com`), under `sv/` and `products/`, which also holds this deposit under `dataset/`. The bucket is catalogued in STAC at `https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen/products/collection.json` and browsable at `https://project-oceanstream-766383-0.lab.dive.edito.eu/`. The processing code and the documentation are at `https://github.com/OceanStreamIO/oceanstream-munkholmen`.

### EK80 MVBS

`Sv(channel, ping_time, depth)` in dB re 1 m⁻¹, averaged in the linear domain over cells of 10 s by 0.5 m. `channel` 0 is 38 kHz and 1 is 200 kHz (`frequency_nominal`). `ping_time` is the start of each 10 s cell and `depth` the top of each 0.5 m cell.

```python
import xarray as xr
ds = xr.open_dataset("ek80/campaign/campaign_mvbs_short_pulse.nc")

# or the zipped Zarr
import zarr
store = zarr.storage.ZipStore("ek80/campaign/campaign_mvbs_short_pulse.zarr.zip", mode="r")
ds = xr.open_zarr(store, consolidated=False)
```

Per-day stores are split by the start time of the raw files, so a day's store runs a few minutes past midnight. The campaign file joins them into one continuous record.

### ADCP

Currents are the instrument's own 5-minute ENU averages. Velocities the instrument marked invalid are NaN; some cells are invalid for much or all of the record. Cells flagged `sidelobe_contaminated` lie in the range affected by the seabed side-lobe echo. The ADCP record ends on 2026-04-13 15:00, and three two-hour files within the period are missing.

### CTD

The CTD record covers 2026-04-13 06:22 to 10:49 only. Temperature, conductivity, pressure and salinity are in physical units. The pH, CDOM, PAR, chlorophyll and turbidity columns are raw sensor voltages, and the oxygen columns are the raw SBE63 phase delay and thermistor voltage; none of these are converted to physical units.

## Processing

Software: echopype (OceanStream fork) and the OceanStream batch pipeline (`processing/run-munkholmen-apr2026.sh`), run in the two steps the OceanStream Denoise Lab uses: the Sv of each day first, then everything from noise removal on, reading that Sv.

1. Raw files converted, and every channel cropped to 100 m range. The recording range alternated between 100 m and 500 m.
2. Sv computed from the complex samples. Sound speed and absorption were derived from measured water properties rather than the EK80 settings: temperature from the ADCP (daily mean, 6.9–7.1 °C) and salinity from the CTD (28.8 PSU), giving about 1472 m/s. Both are near-surface measurements applied to the whole water column.
3. Sv averaged into 0.106 m range bins (3 samples at 38 kHz, 12 at 200 kHz).
4. Noise removal: impulse noise, attenuated signal, transient noise and background noise (De Robertis and Higginbottom 2007), with reference layers placed inside the water column (`processing/munkholmen_denoise.toml`). Samples louder than −10 dB after noise removal are removed as well.
5. Seabed detected at the leading edge of the seabed echo, which is the seabed surface (about 73–74 m, moving with the tide), and masked from 0.5 m above it. Pings left with 80 % or more missing samples were dropped.
6. MVBS computed. The top 1 m is excluded.
7. Echograms drawn for the Sv, the denoised and the pruned data and the MVBS, in three colour maps (`ocean_r`, `ek500`, `jet`).

Steps 4 and 5 are stored as masks over the Sv of step 3 rather than as new copies of it: one flag bit per filter, the background noise level of every ping, and which pings were kept. Opening one of these stores with oceanstream rebuilds the Sv it describes.

## Recording gaps

Pings keep their true timestamps. MVBS cells that contain no pings are not stored, so `ping_time` is irregular across gaps. `ek80/ek80_recording_gaps.csv` lists every gap longer than 5 s:

* 24 outages longer than 30 s (54 minutes in total), caused by drops in the buoy power supply, on 10 April (15:37–17:00 and 21:45–21:58) and 13 April (10:34–11:09 and 13:54).
* About 5 000 pauses of 9–18 s, one per minute starting on the minute (18.6 hours in total).

In the whole-deployment echograms the time axis is collapsed across gaps longer than two minutes, marked by red dashed lines.

## Known limitations

* **200 kHz noise.** The 200 kHz channel has a high noise floor that steps by about 10 dB over minutes. After background-noise removal, 99 % of the 200 kHz MVBS cells hold data between 1 and 10 m, 34 % between 10 and 30 m and 7 % between 30 m and the seabed, 26 % of the water column in all. At 38 kHz, 88 % of the cells above the seabed hold data. Diagonal streaks that sweep through the water column over hours, and full-depth vertical stripes after 13 April 11:00, are interference, not biology.
* **0–12 m.** Both channels show a persistent band of elevated backscatter from the surface to about 12 m, with a sharp lower edge. Its origin has not been established.
* **False bottom on 10 April.** From about 12:10 to 15:38 on 10 April the echosounder pinged every 0.17 s instead of every 1 s. At that rate the second seabed echo of one ping (about 148 m of travel range) arrives during the next ping, about 21 m after its start. The 38 kHz record for that period shows a band of elevated backscatter between about 15 and 35 m that is consistent with this and is absent afterwards. It should not be read as biology.
* **Seabed mask.** The seabed is found on the 38 kHz channel and the mask starts 0.5 m above it on both channels. At 200 kHz the seabed echo starts about one sample (0.1 m) higher, so in 0.4–1.8 % of 200 kHz pings a strong sample of the seabed echo remains just above the mask. Fish within 0.5 m of the seabed are masked with it.
* **Position.** The buoy is moored; no GNSS track was recorded. The position above is the nominal buoy position.
