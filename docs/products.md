# Data products

All times are UTC. The site is the SINTEF OceanLab Munkholmen buoy, 63° 27.45′ N, 010° 22.33′ E, over about 74 m of water. The buoy is moored and recorded no GNSS track, so every product carries the nominal position.

## Instruments

| Instrument | Details |
|---|---|
| Echosounder | Simrad EK80 (software 25.2.3.0), WBT Mini 274022, transducer ES38-18\|200-18CR (serial 266) in the buoy's moonpool, looking down; transducer depth taken as 0 m |
| 38 kHz channel | Split-beam (3 sectors), CW, 1.024 ms pulse, 500 W |
| 200 kHz channel | Single-beam, CW, 0.256 ms pulse, 200 W |
| ADCP | Nortek Signature100 (serial 103128), looking down from about 2.2 m depth; 15 cells of 5 m; echosounder at 70, 90 and 120 kHz |
| CTD | Sea-Bird SBE19plus (serial 01908154) at about 1.1 dbar, with an SBE63 oxygen sensor |

The echosounder was not calibrated with a reference sphere. Sv uses the gain and beam parameters stored in the raw files, the factory values, so absolute levels carry that uncertainty; comparisons within the dataset do not.

## EK80 products

### Sv at the full ping rate

`sv/YYYY-MM-DD/YYYY-MM-DD--short_pulse.zarr`, one store per day, written by stage 4 of the pipeline: `Sv(channel, ping_time, range_sample)` in dB re 1 m⁻¹ as 32-bit floats, with `echo_range` and `depth` in metres. Every channel is cropped to 100 m range, and the samples are averaged in the linear domain into bins of 0.106 m (3 samples at 38 kHz, 12 at 200 kHz), so a day is 2 channels × 66 000–85 000 pings × 932 range bins, 420–540 MB compressed. `channel` 0 is 38 kHz and 1 is 200 kHz; `frequency_nominal` says which. Days are split by the start time of the raw files, so a day's store runs a few minutes past midnight.

### The denoising stores

The three stores under `products/YYYY-MM-DD/` hold what each step removed, not another copy of the Sv:

| Store | Holds |
|---|---|
| `…--denoised.zarr` | `denoise_flags(channel, ping_time, range_sample)`, one bit per filter, and `background_noise(channel, ping_time)`, the noise level subtracted from each ping |
| `…--masked.zarr` | The same flags with the seabed bit set, and `seabed_depth(ping_time)`, the detected seabed line |
| `…--pruned.zarr` | `keep_ping(ping_time)` over the masked store: which pings pruning kept |

The flag bits are impulse 1, attenuation 2, transient 4, background 8, clip 16, seabed 32, other 64 and legacy 128. Each store names the store it stands on and carries a fingerprint of the Sv source, and `oceanstream.echodata.products.resolve_at` rebuilds the Sv it describes (see [reading the stores](data-access.md#reading-the-stores-with-xarray)). The three stores of a day are 17 MB beside the day's 434 MB Sv store.

### MVBS

`Sv(channel, ping_time, depth)` in dB re 1 m⁻¹, averaged in the linear domain over cells of 10 s by 0.5 m, from the pruned data with the top 1 m excluded. `ping_time` is the start of each 10 s cell and `depth` the top of each 0.5 m cell. There is one store per day (`…--mvbs.zarr`, also written as `…--mvbs.nc`) and one for the whole deployment (`products/MUNKHOLMEN_2026/campaign_mvbs_short_pulse.zarr`, 2 × 29 981 × 198 cells), which joins the days into one continuous record. Cells that contain no pings are not stored, so `ping_time` is irregular across the recording gaps. The packaged dataset carries the same MVBS as NetCDF and as zipped Zarr.

### Echograms

For each day, one PNG per channel and colour map (`ocean_r`, `ek500`, `jet`) of the Sv (`raw/`), the denoised data (`denoised/`), the pruned data (`pruned/`) and the MVBS (`mvbs/`), each with a preview of at most 2000 px beside it as `…--thumb.png`; a day's echograms are 85 MB. `products/campaign/` holds the whole-deployment MVBS echograms, in which the time axis is collapsed across gaps longer than two minutes, marked by red dashed lines.

### Recording gaps

`ek80_recording_gaps.csv` lists every interval between consecutive pings longer than 5 s, read from the `.idx` index files: 5 061 rows with the start, the end, the duration, a type and the files on either side.

- 24 outages longer than 30 s, 54 minutes in total, from drops in the buoy's power supply: on 10 April (15:37–17:00 and 21:45–21:58) and 13 April (10:34–11:09 and 13:54).
- 5 037 pauses of 9–18 s, one per minute starting on the minute, 18.6 hours in total.

Pings keep their true timestamps, so the gaps need no flag in the data; they show as missing cells.

## ADCP products

`adcp/munkholmen_adcp_currents_5min.nc` holds the instrument's own 5-minute ENU averages over 15 cells of 5 m. Velocities the instrument marked invalid are NaN, and some cells are invalid for much or all of the record; cells flagged `sidelobe_contaminated` lie in the range affected by the seabed's side-lobe echo. `adcp/munkholmen_adcp_echosounder_sv.nc` holds the Signature100's own echosounder Sv at 70, 90 and 120 kHz. The ADCP record ends on 13 April at 15:00, and three two-hour files within the period are missing.

## CTD products

`ctd/munkholmen_ctd_4hz.csv` is the cleaned full-rate record and `ctd/munkholmen_ctd_1min.csv` its 1-minute means, covering 13 April 06:22 to 10:49 only. Temperature, conductivity, pressure and salinity are in physical units. The pH, CDOM, PAR, chlorophyll and turbidity columns are raw sensor voltages, and the oxygen columns the raw SBE63 phase delay and thermistor voltage; none of these are converted.

The ADCP's temperature and the CTD's salinity are also what the EK80 processing uses for sound speed and absorption: `metadata/ek80_env_params.json` holds the daily values (see [water properties](processing.md#water-properties)).

## The packaged dataset

`dataset/` in the bucket, and `outputs/` in the repository without the large files, is the self-contained deposit: the MVBS of each day and of the whole deployment as NetCDF and zipped Zarr, the MVBS echograms, the gap table, the ADCP and CTD products, the processing files, `MANIFEST.csv` with the size and SHA-256 of every file, and a README that describes the deposit on its own. The full-resolution Sv, the denoising stores and the echograms of the other stages are only in the bucket.

## Known limitations

- **200 kHz noise.** The 200 kHz channel has a high noise floor that steps by about 10 dB over minutes. After background-noise removal, 99 % of its MVBS cells hold data between 1 and 10 m, 34 % between 10 and 30 m and 7 % between 30 m and the seabed, 26 % of the water column in all; at 38 kHz, 88 % of the cells above the seabed hold data. Diagonal streaks that sweep through the water column over hours, and full-depth vertical stripes after 13 April 11:00, are interference, not biology.
- **0–12 m.** Both channels show a persistent band of elevated backscatter from the surface to about 12 m, with a sharp lower edge. Its origin has not been established.
- **False bottom on 10 April.** From about 12:10 to 15:38 on 10 April the echosounder pinged every 0.17 s instead of every 1 s. At that rate the second seabed echo of one ping (about 148 m of travel range) arrives during the next ping, about 21 m after its start, and the 38 kHz record for that period shows a band of elevated backscatter at 15–35 m that is consistent with this and absent afterwards. It should not be read as biology.
- **Seabed mask.** The seabed is found on the 38 kHz channel and the mask starts 0.5 m above it on both channels. At 200 kHz the seabed echo starts about one sample (0.1 m) higher, so in 0.4–1.8 % of 200 kHz pings a strong sample of the seabed echo remains just above the mask. Fish within 0.5 m of the seabed are masked with it.
- **Calibration.** No reference-sphere calibration; Sv is on the factory gains.
- **Companion data.** The ADCP record ends on 13 April and the CTD covers a few hours of that day; the water properties applied to the whole deployment come from those records.
