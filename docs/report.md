# Technical report: the Munkholmen EK80 deployment

Status as of 6 October 2026. This report describes work package 2 of the project *Digital Solutions for Automated Monitoring of Seaweed Farm Operations*, and the parts of work package 1 that the deployment exercised: what was planned, what was done, what the data showed, what was learned, and what remains open. It is written to serve as the technical part of the project report. The dataset itself is described in [Data products](products.md) and the processing in [Processing](processing.md).

## 1. The project

*Digital Solutions for Automated Monitoring of Seaweed Farm Operations* is a twelve-month project (2026) of Pine View Software AS (PVS), the company behind OceanStream, with SINTEF Ocean AS as R&D supplier, co-funded by Akershus fylkeskommune (AFK). Its aim is an automated way of monitoring seaweed farms: uncrewed surface vessels and fixed sensors collect acoustic and visual data, and an edge-to-cloud pipeline analyses them in near real time to track the growth of the canopy as an estimate of harvestable biomass. The work packages are:

1. Software architecture and data standards (PVS): the OceanStream edge–cloud pipeline for farm monitoring, stable acquisition from echosounders and sonars with little connectivity, and the metadata and quality control that reproducible analytics and model training need.
2. A field test with an EK80 echosounder at the OceanLab Munkholmen observatory (SINTEF Ocean): a benchmark water-column dataset for model validation, and the platform's noise and best operating modes.
3. Biomass estimates of seaweed with a sonar on an uncrewed surface vessel at a seaweed farm at Skarvøya (SINTEF Ocean).
4. A feasibility study of machine-learning models for biomass from sonar features, canopy area from images and growth from time series (PVS).
5. Reporting, TRL 6 verification and exploitation (SINTEF Ocean and PVS): memos, a KPI sheet, open datasets and metadata, and a commercialisation plan.

This report is about work package 2. Its research question was which edge device settings ensure stable logging over five days with an intermittent internet connection, and its method was to put the echosounder in the buoy's moonpool for five days, logging internally, and to collate and share the data together with the observatory's own data from the period, for PVS to use in the software and data integration of OceanStream and to validate its store-and-forward behaviour. The pipeline that processed the data, the formats the products use and the Denoise Lab that ran it belong to work package 1, so the deployment was also their first test on data from a fixed platform in a fjord.

## 2. The deployment

SINTEF Ocean's OceanLab Munkholmen buoy is moored in Trondheim Fjord at 63° 27.45′ N, 010° 22.33′ E, over about 74 m of water, and carries a Nortek Signature100 ADCP and a Sea-Bird SBE19plus CTD whose data the observatory makes available. A Simrad EK80 WBT Mini (software 25.2.3.0) with an ES38-18|200-18CR transducer, loaned by NTNU, was installed in the buoy's moonpool looking down: 38 kHz split-beam and 200 kHz single-beam, both CW, with 1.024 ms and 0.256 ms pulses at 500 W and 200 W. Its transducer depth was taken as 0 m. The echosounder logged to its own storage; the raw files were then uploaded to an Azure file share, from which the cloud pipeline reads them directly, and the ADCP and CTD files for the period were provided alongside.

Recording ran from 10 April 2026 11:29 UTC to 14 April 00:25 UTC, 3.5 days over five calendar days, and produced 1 196 raw files of 124 GB.

| Day | Raw files | Pings | Sv store, as published |
|---|---|---|---|
| 10 April | 193 | 85 485 | 543 MB |
| 11 April | 200 | 66 032 | 418 MB |
| 12 April | 367 | 68 365 | 434 MB |
| 13 April | 426 | 66 914 | 424 MB |
| 14 April | 10 | 952 | 6 MB |
| Total | 1 196 | 287 748 | 1.83 GB |

The ping interval was 1 s except between 12:10 and 15:38 on 10 April, when it was 0.17 s, and the recording range alternated between 100 m and 500 m. The ADCP record ends on 13 April at 15:00, with three two-hour files missing within the period, and the CTD record covers 13 April 06:22–10:49 only.

## 3. What was done

**Edge processing.** The full dataset was first processed on the device that collected it, an NVIDIA Jetson Orin NX with 16 GB of memory, with echopype and the OceanStream batch pipeline, in about six hours. Fitting a day of two-channel complex EK80 data into 16 GB set the shape of the processing that was kept afterwards: every file cropped to 100 m range, the Sv averaged into 0.106 m range bins and stored as 32-bit floats, and the data handled 250 pings at a time.

**Cloud processing.** On 4 October 2026 the same pipeline was run again on the Prefect worker of the OceanStream Denoise Lab on the EDITO DataLab, the way the lab runs every survey: the raw files read from the Azure file share, the Sv of each day written to object storage first, one process per day, then everything from denoising on, reading that Sv. The run took 6.3 hours, one day at a time with up to 8 CPUs. It used measured water properties for sound speed and absorption, denoising reference layers placed inside the water column, a seabed mask, and no GPS merge, NASC or map tiles, since the platform is moored. On 5 October the products step alone was run again (1.8 hours) with the seabed line moved to the leading edge of the seabed echo (section 4.4).

**Publication.** The Sv stores, the denoising stores, the MVBS and the echograms were published in a public prefix of the project's bucket at CloudFerro, 2.4 GB in all, with a STAC catalogue (one Item per day) and a STAC Browser instance on the EDITO DataLab. A packaged dataset of the small products (0.2 GB) was assembled for deposit, and this repository holds the processing code, the catalogue and the documentation. A Zenodo deposit is planned.

**The lab.** The deployment was set up in the Denoise Lab as a survey with the same processing settings, with the published configuration as a preset and a more sensitive variant as a trial, so the processing can be repeated and varied on any day from a browser. The Sv the lab computes for a day matches the published store exactly.

## 4. Findings

### 4.1 Logging stability, the research question

The echosounder logged for the whole deployment, but not continuously, and the data show what interrupted it.

- **Power.** 24 outages longer than 30 s, 54 minutes in total, from drops in the buoy's power supply, in four episodes: on 10 April 15:37–17:00 and 21:45–21:58, and on 13 April 10:34–11:09 and at 13:54. Recording resumed after each.
- **A pause every minute.** 5 037 pauses of 9–18 s, one per minute starting on the minute, 18.6 hours in total, more than a fifth of the recording time. Their cause was not established during the deployment. They do not harm the processing, since pings keep their true timestamps and the MVBS simply has no cells there, but they are the single largest loss of data.
- **Range mode.** The recording range alternated between 100 m and 500 m over a 74 m seabed. The 500 m files hold five times the samples for no additional information, and had to be cropped to 100 m before the days could be processed alike.
- **Ping rate.** For 3.5 hours on 10 April the echosounder pinged every 0.17 s instead of every 1 s. At 0.17 s the second seabed echo of one ping arrives during the next, 21 m after its start, and the 38 kHz record for those hours shows a false bottom at 15–35 m that is absent otherwise. The fast rate also made 10 April the day with the most pings.
- **Environment settings.** The EK80 software held its default water properties, 10 °C and 35 PSU, where the measured values were 6.9–7.1 °C and 28.8 PSU. Sound speed and absorption were recomputed from the measured values in processing (section 4.2).

For the next deployment this suggests: a stable power supply for the echosounder, or at least a log of the supply voltage; one recording range chosen for the site depth (100 m here) and one ping interval, held for the whole deployment; the environment settings in the EK80 software set to the measured water properties, or the measured properties recorded so that processing can apply them; and a check of the logging software's duty cycle before deployment. Beyond the gaps, the record is complete, and the store-and-forward path — internal logging, upload of the raw files to the file share, processing from the share — worked without loss.

### 4.2 Water properties and calibration

echopype applies user-supplied temperature, salinity, pressure and pH only when all four are given, and otherwise keeps the raw file's values without a warning. With the ADCP's daily mean temperature, the CTD's salinity, a mid-column pressure and a nominal pH, the sound speed is about 1472 m/s. Both measurements are near-surface values applied to the whole column, and the CTD covered a few hours of one day, so one salinity serves the whole deployment. The echosounder was not calibrated with a reference sphere, so the Sv is on the factory gains; absolute levels carry that uncertainty, comparisons within the dataset do not. A sphere calibration before the next deployment would remove it.

### 4.3 Noise, and what the water column looks like

The 38 kHz channel is usable through the water column: after denoising, 53–54 % of its water-column cells on 13 April survive at the full resolution, and 88 % of its MVBS cells above the seabed hold data. The 200 kHz channel is dominated by noise. Its noise floor is high and steps by about 10 dB over minutes, and after background-noise removal only 8.5 % of its cells before 11:00 on 13 April and 15.7 % after survive at the full resolution; in the MVBS, 99 % of its cells hold data between 1 and 10 m, 34 % between 10 and 30 m and 7 % below. Diagonal streaks that sweep through the water column over hours, and full-depth vertical stripes from 13 April 11:00, are interference, not biology; their source was not identified. Both channels show a band of elevated backscatter from the surface to about 12 m with a sharp lower edge, whose origin has not been established.

Of the four filters, the three that work by masking — impulse noise, attenuated signal and transient noise — remove well under 1 % of the cells with the thresholds of the published configuration; background-noise removal does almost all the work. A trial with more sensitive thresholds (impulse 8 dB, transient 6 dB) changed nothing at 38 kHz and only thinned the 200 kHz stripes after 11:00, where its transient filter flagged 6 % of the cells, so the published thresholds were kept. The reference layers of the standard open-ocean configuration (the attenuation reference at 400–500 m, the transient start at 200–250 m) lie below the seabed and had to be moved inside the 0–70 m column; a shallow site needs its own configuration, which the repository carries.

### 4.4 Seabed detection

The pipeline's composite seabed detector returns, by default, the deepest strong sample of the seabed echo. On this data that sample lies 4–6 m below the seabed surface (5.4 m in the median on 13 April, 3.7–6.2 m between the 1st and 99th percentiles) and moves with the length of the echo's tail, so the line is both biased and jittery. With the 6 m offset of the first run, a strong (louder than −50 dB) echo sat within 3 m above the mask in 2–13 % of pings depending on the day, and the smoothing spread short excursions into ramps. A second pick was added to oceanstream, the leading edge of the echo — the sample where it starts, which is the seabed surface — smoothed with a running median that drops short excursions instead of spreading them. With it and a 0.5 m offset the line follows the tide (72.7–74.6 m over the deployment) without jumps, no seabed echo is left unmasked below the line, and a strong sample touches the mask in at most 0.08 % of pings at 38 kHz and in 0.4–1.8 % at 200 kHz, where the echo starts one sample (0.1 m) higher. The products were remade with it.

### 4.5 Serving the data publicly

Zarr v3 stores in object storage worked well for the products, with one lesson: the bucket answers 403 rather than 404 for a key that does not exist, even in a prefix that is public and listable. xarray therefore fails to open a store unless told `zarr_format=3`, because it looks for Zarr v2 metadata first, and a store with chunks that Zarr left unwritten because they held only the fill value cannot be read in full. The run now writes those chunks (29 were missing across 8 stores), every Zarr asset in the STAC catalogue carries the open arguments, and the STAC documents are served as `application/json`, for which the oceanstream STAC writer was fixed. Storing the denoising stages as masks over a shared Sv keeps the products small — the three stores of a day are 17 MB beside a 434 MB Sv store — and lets the lab and the published run share one Sv.

### 4.6 What the pipeline and the lab gained

The first survey from a fixed platform in a shallow fjord drove changes in oceanstream and in the Denoise Lab that are now general:

- in oceanstream: options for the range crop, the range binning, 32-bit Sv, the chunking and per-day water properties; the choice of seabed line; the STAC content types; and a way to redo the products step on an existing Sv;
- in the Denoise Lab: Sv settings and run defaults per survey, with the options above; pulse categories per survey; a seabed mask with a choice of line and offset; the GPS track as a survey setting, or none; a batch deployment that runs a whole script on the worker; a Processing options card and navigation between a survey's days on the Run and Runs pages; and the shared Sv shown per survey in the Files page.

## 5. Deliverables and status

| Deliverable | Status |
|---|---|
| EK80 raw data, 124 GB | Collected; on the Azure file share; not distributed |
| Sv at the full ping rate, denoising stores, MVBS, echograms | Public in the bucket; remade on 5 October 2026 |
| STAC catalogue and browser | Public: the catalogue in the bucket and in `stac/`, the browser on the EDITO DataLab |
| Packaged dataset (`dataset/`, 0.2 GB, with manifest and README) | In the bucket; Zenodo deposit planned, record metadata prepared |
| Processing code, configuration and documentation | This repository (MIT); the pipeline changes in oceanstream-cli, to be released |
| The deployment in the Denoise Lab | Survey, presets and the published Sv set up |
| SINTEF Ocean memo on the data collection and the observatory data (work package 5) | SINTEF Ocean |
| KPI sheet and commercialisation plan (work package 5) | PVS, pending |

## 6. Open points

- The authors and contributors of the dataset record, and the Zenodo deposit with its DOI.
- A release of oceanstream on PyPI that includes the changes made for this dataset, and the open-source release of the Denoise Lab.
- A reference-sphere calibration before the next deployment, and the EK80 environment settings set to measured values.
- The source of the 200 kHz interference and of the 0–12 m band; the ADCP's own 70–120 kHz echosounder record may help.
- The per-minute pause in logging.
- The dataset's use as a benchmark in work package 4, and the transfer of the method to the sonar on the uncrewed surface vessel in work package 3.
