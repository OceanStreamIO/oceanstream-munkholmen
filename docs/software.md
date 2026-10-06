# Software

## oceanstream

[oceanstream-cli](https://github.com/OceanStreamIO/oceanstream-cli) is the OceanStream processing package: the batch pipeline `scripts/batch_processing/process_from_raw.py` that made these products, the product stores (`oceanstream.echodata.products`), the seabed detectors (`oceanstream.echodata.seabed`), the STAC writer (`oceanstream.stac.echodata`), and the tools for other instruments and for GeoParquet tracks. It is on PyPI as [`oceanstream`](https://pypi.org/project/oceanstream/) (0.1.1, 17 January 2026), but that release predates this work: the stores of masks over a shared Sv, the STAC catalogue, the two-step S3 layout, the shallow-site options (`--max-range-m`, `--sv-range-bin-m`, `--sv-float32`, `--env-params-file`, `--seabed-mask-offset`) and the leading-edge seabed line (`--seabed-line`, October 2026) all came later. Install it from the repository, as in [Reproducing](processing.md#reproducing), until a release includes them.

## echopype

The pipeline converts the raw files and computes Sv with [echopype](https://github.com/OSOceanAcoustics/echopype), through the `oceanstream-integration` branch of the OceanStream fork, [OceanStreamIO/echopype](https://github.com/OceanStreamIO/echopype), which the pipeline is run against; this run used commit c93006b3. echopype also supplies the denoising methods and the MVBS computation.

## The Denoise Lab

The OceanStream Denoise Lab is a web application for running the pipeline on a survey day with a preset of parameters and comparing the echograms it produces, stage by stage and preset against preset, from a browser. It queues runs on Prefect, executes them one at a time on a worker, keeps every product in object storage, and renders the echograms of each stage; the parameters are declared once in a schema that the form, the validator and the TOML the pipeline loads all read from, and a preset can be exported as TOML or JSON. For this dataset it gained survey-level processing settings and run defaults, a seabed mask with a choice of seabed line, pulse categories per survey, a batch deployment, and per-survey views of the shared Sv (see [The Denoise Lab](denoise-lab.md)).

It runs on the EDITO DataLab for the OceanStream project. It will be released as open source under the [OceanStreamIO](https://github.com/OceanStreamIO) organisation on GitHub, and it is growing from a tool for tuning the denoising into a web lab for the whole echodata processing chain: surveys and their sources, the Sv computation, denoising, the seabed and pruning, MVBS and NASC, and the products, files and catalogues that come out.

## The EDITO DataLab

The [EDITO DataLab](https://datalab.dive.edito.eu) is the platform of the European Digital Twin Ocean for running services next to ocean data: a Kubernetes cluster managed with Onyxia, with object storage at CloudFerro. The OceanStream project space on it hosts the Denoise Lab and its Prefect server, the bucket the products are in, and the [STAC Browser](https://project-oceanstream-766383-0.lab.dive.edito.eu/) that shows the catalogue. The processing of this dataset ran there, on the lab's worker.

## Versions

`requirements.txt` in the repository pins the Python packages of the run: numpy 2.0.2, pandas 2.3.3, xarray 2026.7.0, dask 2026.8.0, zarr 3.4.0, numcodecs 0.14.1, s3fs 2025.3.2 and the rest. xarray 2026.9 and later cannot write the converted EchoData (an unexpected `compressor` encoding), so the pin stays below it. The stores are Zarr v3, and the STAC documents follow STAC 1.0 with the processing and xarray-assets extensions.
