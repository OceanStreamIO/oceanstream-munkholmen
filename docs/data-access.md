# Getting the data

Everything the run produced is in one public prefix of an S3 bucket at CloudFerro (Warsaw), readable and listable without credentials.

| | |
|---|---|
| S3 | `s3://oceanstream-bucket/munkholmen/`, endpoint `https://s3.waw3-1.cloudferro.com` (region `waw3-1`) |
| HTTPS | `https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen/` |
| STAC catalogue | `https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen/products/collection.json` |
| STAC Browser | <https://project-oceanstream-766383-0.lab.dive.edito.eu/> |

## What is where

| Prefix | Holds | Size |
|---|---|---|
| `sv/YYYY-MM-DD/` | Sv at the full ping rate, one Zarr store per day | 1.8 GB, 9 500 objects |
| `products/YYYY-MM-DD/` | The denoised, seabed-masked and pruned stores, the MVBS (Zarr and NetCDF), the echograms of each stage, and the day's STAC Item | 0.6 GB, 9 100 objects, all days together |
| `products/MUNKHOLMEN_2026/` | The whole-deployment MVBS (Zarr) | 38 MB |
| `products/campaign/` | The whole-deployment echograms | |
| `products/collection.json` | The STAC Collection | |
| `dataset/` | The packaged dataset: the MVBS as NetCDF and zipped Zarr, the MVBS echograms, the ADCP and CTD products, the gap table, the dataset README, the processing files, and `MANIFEST.csv` with the SHA-256 of every file | 0.2 GB, 65 files |

The denoised, masked and pruned stores do not repeat the Sv: they hold what each step removed (see [the denoising stores](products.md#the-denoising-stores)), and `oceanstream` rebuilds the Sv from them and the `sv/` store when they are opened.

## The STAC catalogue

The Collection has one Item per day, `products/YYYY-MM-DD/item.json`, whose assets are that day's Sv store, the three denoising stores, the MVBS as Zarr and NetCDF, and every echogram; the whole-deployment MVBS and echograms and the files of the packaged dataset are assets of the Collection itself. Every Zarr asset carries `xarray:open_kwargs` (`{"engine": "zarr", "zarr_format": 3}`), so a STAC client that opens assets with xarray opens them correctly. The links inside the bucket are relative; the copy under `stac/` in the repository has every link absolute, so it opens from a clone.

The STAC Browser above is an instance on the EDITO DataLab pointed at this catalogue. The [public STAC Browser](https://radiantearth.github.io/stac-browser/) opens the catalogue URL as well.

## Reading the stores with xarray

```python
import xarray as xr

base = "https://oceanstream-bucket.s3.waw3-1.cloudferro.com/munkholmen"

# the whole-deployment MVBS and one day's MVBS
campaign = xr.open_zarr(f"{base}/products/MUNKHOLMEN_2026/campaign_mvbs_short_pulse.zarr", zarr_format=3)
mvbs_day = xr.open_zarr(f"{base}/products/2026-04-12/2026-04-12--short_pulse--mvbs.zarr", zarr_format=3)

# a day's Sv at the full ping rate
sv = xr.open_zarr(f"{base}/sv/2026-04-12/2026-04-12--short_pulse.zarr", zarr_format=3)
```

`zarr_format=3` is required. Without it xarray first looks for the Zarr v2 files (`.zmetadata`, `.zgroup`), and this bucket answers 403 rather than 404 for a key that does not exist, which xarray reports as an error instead of going on to try v3. For the same reason every chunk of every store exists, including the chunks that hold only the fill value, which Zarr normally leaves unwritten: the run writes them at the end (`processing/fill_empty_chunks.py`).

The denoised, masked and pruned stores need `oceanstream` to be rebuilt into Sv:

```python
import xarray as xr
from oceanstream.echodata.products import resolve_at

S3 = {"anon": True, "client_kwargs": {"endpoint_url": "https://s3.waw3-1.cloudferro.com"}}

def open_public(uri):
    return xr.open_zarr(uri, zarr_format=3, storage_options=S3)

pruned = "s3://oceanstream-bucket/munkholmen/products/2026-04-12/2026-04-12--short_pulse--pruned.zarr"
sv = resolve_at(open_public(pruned), pruned, open_public)   # the pruned, seabed-masked, denoised Sv
```

## Downloading

The files under `dataset/` are plain NetCDF, zipped Zarr, CSV and PNG files that download over HTTPS one at a time, or all together with the AWS CLI:

```bash
aws s3 sync --no-sign-request --endpoint-url https://s3.waw3-1.cloudferro.com --region us-east-1 \
    s3://oceanstream-bucket/munkholmen/dataset/ munkholmen-dataset/
```

The CLI needs a `--region`; any value works. A Zarr store is a folder of many small objects, not one file, so its URL does not download in a browser. Copy a store the same way, and the copy opens with a plain `xr.open_zarr`:

```bash
aws s3 sync --no-sign-request --endpoint-url https://s3.waw3-1.cloudferro.com --region us-east-1 \
    s3://oceanstream-bucket/munkholmen/products/MUNKHOLMEN_2026/campaign_mvbs_short_pulse.zarr campaign_mvbs_short_pulse.zarr
```

The packaged dataset carries each MVBS store as a `.zarr.zip` as well, readable in place with `zarr.storage.ZipStore` and the right shape for a Zenodo deposit, which stores flat files.

## Where the dataset is published

- **EDITO DataLab.** The bucket, the STAC Browser and the Denoise Lab that made the products are in the OceanStream project space on the [EDITO DataLab](https://datalab.dive.edito.eu), the platform of the European Digital Twin Ocean.
- **This repository.** The small products (`outputs/`), the catalogue (`stac/`), the processing code and this documentation.
- **Zenodo.** A deposit of the packaged dataset (`dataset/`) is planned; `metadata/zenodo.json` holds the record's metadata. The DOI will be added to the README and to the catalogue once the deposit exists.
