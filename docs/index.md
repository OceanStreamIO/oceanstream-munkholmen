# OceanStream Edge deployment at Munkholmen Ocean Observatory

Documentation for the echosounder deployment on the SINTEF OceanLab Munkholmen buoy in Trondheim Fjord, 10–14 April 2026: where the data are, what the products contain, how they were made, and what the deployment taught us.

A Simrad EK80 WBT Mini (38 and 200 kHz) pinged from the buoy's moonpool for 3.5 days while the buoy's own ADCP and CTD recorded currents and water properties. The raw files were first processed on the edge device that collected them, an NVIDIA Jetson Orin NX with 16 GB of memory, and then again on the OceanStream Denoise Lab on the EDITO DataLab, the way the lab runs every survey: raw files read from an Azure file share, every product written to object storage. The products are public.

| | |
|---|---|
| Site | SINTEF OceanLab Munkholmen buoy, 63° 27.45′ N, 010° 22.33′ E, Trondheim Fjord, Norway |
| Period | 2026-04-10 11:29 to 2026-04-14 00:25 UTC |
| Echosounder | Simrad EK80 WBT Mini with an ES38-18\|200-18CR transducer: 38 kHz split-beam and 200 kHz single-beam, CW |
| Companion sensors | Nortek Signature100 ADCP (currents and a 70/90/120 kHz echosounder), Sea-Bird SBE19plus CTD |
| Raw data | 1 196 EK80 files, 124 GB, 287 748 pings (not distributed) |
| Products | Sv at the full ping rate (1.8 GB), denoising stores, MVBS and echograms (0.6 GB), packaged dataset (0.2 GB) |
| Where | `s3://oceanstream-bucket/munkholmen/` at CloudFerro, public, with a STAC catalogue and a STAC Browser |
| Licence | Code MIT, data CC0 1.0 |

## Pages

- [Getting the data](data-access.md) — the bucket, the STAC catalogue and browser, reading the stores with xarray, downloading, and where the dataset is published.
- [Data products](products.md) — every product, its variables and format, the recording gaps and the known limitations.
- [Processing](processing.md) — the pipeline, the site settings, the denoising configuration, the seabed mask, the scripts, and how to reproduce the run.
- [The Denoise Lab](denoise-lab.md) — the survey and presets set up in the OceanStream Denoise Lab, and what trying other parameters showed.
- [Software](software.md) — oceanstream, the echopype fork, the Denoise Lab web application and the EDITO DataLab.
- [Technical report](report.md) — the project this deployment belongs to, how it went, what was found, and what is still open.

## Citing

A Zenodo deposit of the packaged dataset is planned. Until it has a DOI, cite the repository and the catalogue: *OceanStream Edge deployment at Munkholmen Ocean Observatory – EK80, ADCP and CTD, Trondheim Fjord, 10–14 April 2026*, <https://github.com/OceanStreamIO/oceanstream-munkholmen>, STAC catalogue <https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen/products/collection.json>.

## Funding

This deployment is work package 2 of *Digital Solutions for Automated Monitoring of Seaweed Farm Operations*, a project of Pine View Software AS with SINTEF Ocean AS as R&D supplier, co-funded by Akershus fylkeskommune (AFK). The [technical report](report.md) describes the project and the outcome. The EK80 WBT Mini was loaned by NTNU.
