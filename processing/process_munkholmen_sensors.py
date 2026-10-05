#!/usr/bin/env python
"""Process the ADCP and CTD data that accompany the Munkholmen EK80 deployment.

Inputs (raw, read-only):
  * Nortek Signature100 ``.ad2cp`` files, one pair per two hours:
      ``YYMMDDHHMM_avgd.ad2cp``  5-minute averaged currents (ENU)
      ``YYMMDDHHMM.ad2cp``       burst data incl. the 70/90/120 kHz echosounder
  * Sea-Bird SBE19plus CSV logs (``ctd_*.csv``) written by the buoy logger.

Outputs:
  adcp/munkholmen_adcp_currents_5min.nc     currents, ENU, 5-minute averages
  adcp/munkholmen_adcp_echosounder_sv.nc    Sv at 70/90/120 kHz
  ctd/munkholmen_ctd_4hz.csv                cleaned full-rate CTD record
  ctd/munkholmen_ctd_1min.csv               1-minute means
  ek80_env_params.json                      temperature/salinity for the EK80 Sv

Only files that overlap the EK80 recording period are processed.

Usage:
  python process_munkholmen_sensors.py \
      --adcp-dir ~/data/raw/adcp --ctd-dir ~/data/raw/ctd \
      --out-dir ~/data/munkholmen_2026/sensors
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger("munkholmen_sensors")

# EK80 recording period (UTC), from the first and last ping.
EK80_START = datetime(2026, 4, 10, 11, 29)
EK80_END = datetime(2026, 4, 14, 0, 26)

# Buoy position: 63° 27.45' N, 010° 22.33' E
SITE_ATTRS = {
    "platform": "SINTEF OceanLab Munkholmen buoy, Trondheim Fjord, Norway",
    "geospatial_lat": 63.4575,
    "geospatial_lon": 10.3722,
}

ADCP_FILE_SPAN = timedelta(hours=2)
ADCP_INVALID_VELOCITY = -32.0  # int16 fill value (-32768 mm/s) after scaling
# Seabed range seen by the EK80 (m). ADCP cells beyond
# range * cos(beam angle) are contaminated by the seabed side-lobe echo.
SEABED_RANGE_M = 74.7
ADCP_BEAM_ANGLE_DEG = 25.0

CTD_COLUMNS = {
    "Temperature": "temperature_degC",
    "Conductivity": "conductivity_S_per_m",
    "Pressure": "pressure_dbar",
    "Volt0": "ph_raw_V",
    "Volt1": "cdom_raw_V",
    "Volt2": "par_raw_V",
    "Volt4": "chlorophyll_raw_V",
    "Volt5": "turbidity_raw_V",
    "SBE63": "oxygen_phase_delay_us",
    "SBE63Temperature": "oxygen_thermistor_V",
    "Salinity": "salinity_PSU",
    "Timestamp": "time",
}
# Plausible ranges used to reject lines corrupted on the serial link.
CTD_VALID_RANGES = {
    "temperature_degC": (-2.0, 30.0),
    "conductivity_S_per_m": (0.0, 7.0),
    "pressure_dbar": (-1.0, 200.0),
    "salinity_PSU": (0.0, 40.0),
}


def _adcp_file_start(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.name[:10], "%y%m%d%H%M")
    except ValueError:
        return None


def _overlapping_adcp_files(adcp_dir: Path, suffix: str) -> list[Path]:
    files = []
    for path in sorted(adcp_dir.glob(f"*{suffix}")):
        start = _adcp_file_start(path)
        if start is None:
            continue
        if suffix == ".ad2cp" and path.stem.endswith("_avgd"):
            continue
        if start < EK80_END and start + ADCP_FILE_SPAN > EK80_START:
            files.append(path)
    return files


def process_adcp_currents(adcp_dir: Path, out_dir: Path) -> Path | None:
    from oceanstream.adcp.ad2cp_reader import read_ad2cp_velocity

    files = _overlapping_adcp_files(adcp_dir, "_avgd.ad2cp")
    logger.info("ADCP currents: %d averaged files overlap the EK80 period", len(files))
    parts = []
    for path in files:
        try:
            ds = read_ad2cp_velocity(path)
        except Exception as exc:
            logger.warning("  Skipping %s: %s", path.name, exc)
            continue
        if ds.attrs.get("coord_sys") != "ENU":
            logger.warning("  Skipping %s: coordinate system is %s, expected ENU",
                           path.name, ds.attrs.get("coord_sys"))
            continue
        parts.append(ds)
    if not parts:
        return None

    raw = xr.concat(parts, dim="time").sortby("time")
    raw = raw.isel(time=np.unique(raw["time"].values, return_index=True)[1])
    raw = raw.sel(time=slice(np.datetime64(EK80_START), np.datetime64(EK80_END)))

    velocity = raw["velocity"].where(raw["velocity"] > ADCP_INVALID_VELOCITY)
    east, north = velocity.isel(beam=0), velocity.isel(beam=1)
    cell_range = raw["depth"].values
    transducer_depth = float(raw["pressure"].mean())
    max_clean_range = (SEABED_RANGE_M - transducer_depth) * np.cos(np.deg2rad(ADCP_BEAM_ANGLE_DEG))

    ds = xr.Dataset(
        {
            "east_velocity": (("time", "cell"), east.values,
                              {"units": "m s-1", "long_name": "Eastward current velocity"}),
            "north_velocity": (("time", "cell"), north.values,
                               {"units": "m s-1", "long_name": "Northward current velocity"}),
            "up_velocity_1": (("time", "cell"), velocity.isel(beam=2).values,
                              {"units": "m s-1", "long_name": "Upward velocity, beam pair 1"}),
            "up_velocity_2": (("time", "cell"), velocity.isel(beam=3).values,
                              {"units": "m s-1", "long_name": "Upward velocity, beam pair 2"}),
            "current_speed": (("time", "cell"), np.hypot(east, north).values,
                              {"units": "m s-1", "long_name": "Horizontal current speed"}),
            "current_direction": (
                ("time", "cell"),
                (np.degrees(np.arctan2(east, north)) % 360).values,
                {"units": "degree", "long_name": "Direction the current flows towards, clockwise from north"},
            ),
            "amplitude": (("time", "cell", "beam"), raw["amplitude"].values,
                          {"units": "counts", "long_name": "Echo amplitude (0.5 dB per count)"}),
            "correlation": (("time", "cell", "beam"), raw["correlation"].values,
                            {"units": "percent", "long_name": "Signal correlation"}),
            "sidelobe_contaminated": (
                ("cell",), cell_range > max_clean_range,
                {"long_name": "Cell lies beyond the range free of seabed side-lobe echo"},
            ),
            "temperature": ("time", raw["temperature"].values, {"units": "degC"}),
            "pressure": ("time", raw["pressure"].values, {"units": "dbar"}),
            "sound_speed": ("time", raw["sound_speed"].values, {"units": "m s-1"}),
            "heading": ("time", raw["heading"].values, {"units": "degree"}),
            "pitch": ("time", raw["pitch"].values, {"units": "degree"}),
            "roll": ("time", raw["roll"].values, {"units": "degree"}),
        },
        coords={
            "time": raw["time"].values,
            "range": ("cell", cell_range, {"units": "m", "long_name": "Range from the transducer head"}),
            "depth": ("cell", cell_range + transducer_depth,
                      {"units": "m", "long_name": "Depth below the surface (range + mean transducer depth)"}),
            "beam": raw["beam"].values,
        },
        attrs={
            **SITE_ATTRS,
            "title": "Munkholmen buoy ADCP currents, 5-minute averages, April 2026",
            "instrument": "Nortek Signature100, serial 103128, downward-looking",
            "coordinate_system": "ENU",
            "averaging_interval_s": 300,
            "cell_size_m": float(raw.attrs["cell_size_m"]),
            "blanking_m": float(raw.attrs["blanking_m"]),
            "mean_transducer_depth_m": round(transducer_depth, 2),
            "source_files": ", ".join(p.name for p in files),
            "comment": "Velocities the instrument flagged invalid are NaN. "
                       "Cells with sidelobe_contaminated = 1 should not be used.",
        },
    )
    out = out_dir / "adcp" / "munkholmen_adcp_currents_5min.nc"
    out.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out)
    logger.info("  Wrote %s (%d profiles, %s → %s)", out, ds.sizes["time"],
                str(ds.time.values[0])[:16], str(ds.time.values[-1])[:16])
    return out


def process_adcp_echosounder(adcp_dir: Path, out_dir: Path, salinity: float) -> Path | None:
    from oceanstream.adcp.ad2cp_reader import read_ad2cp
    from oceanstream.adcp.sv_computation import compute_sv

    files = _overlapping_adcp_files(adcp_dir, ".ad2cp")
    logger.info("ADCP echosounder: %d burst files overlap the EK80 period", len(files))
    parts = []
    for path in files:
        try:
            parts.append(compute_sv(read_ad2cp(path), salinity=salinity))
        except Exception as exc:
            logger.warning("  Skipping %s: %s", path.name, exc)
    if not parts:
        return None

    ds = xr.concat(parts, dim="ping_time", combine_attrs="drop_conflicts").sortby("ping_time")
    ds = ds.isel(ping_time=np.unique(ds["ping_time"].values, return_index=True)[1])
    ds = ds.sel(ping_time=slice(np.datetime64(EK80_START), np.datetime64(EK80_END)))
    ds.attrs.update({
        **SITE_ATTRS,
        "title": "Munkholmen buoy ADCP echosounder Sv (70, 90, 120 kHz), April 2026",
        "instrument": "Nortek Signature100, serial 103128, downward-looking",
        "salinity_used_PSU": salinity,
        "source_files": ", ".join(p.name for p in files),
    })
    ds.attrs.pop("source_file", None)
    out = out_dir / "adcp" / "munkholmen_adcp_echosounder_sv.nc"
    out.parent.mkdir(parents=True, exist_ok=True)
    encoding = {v: {"zlib": True, "complevel": 4} for v in ds.data_vars if ds[v].ndim >= 2}
    ds.to_netcdf(out, encoding=encoding)
    logger.info("  Wrote %s (%d pings, %s → %s)", out, ds.sizes["ping_time"],
                str(ds.ping_time.values[0])[:16], str(ds.ping_time.values[-1])[:16])
    return out


def _read_ctd_csv(path: Path) -> pd.DataFrame:
    """Read one logger CSV, skipping the instrument status block before the header."""
    with open(path, errors="replace") as fh:
        lines = fh.readlines()
    header = next(i for i, line in enumerate(lines) if line.strip().startswith("Temperature,"))
    df = pd.read_csv(path, skiprows=header, skipinitialspace=True, on_bad_lines="skip",
                     dtype=str, encoding_errors="replace")
    df.columns = df.columns.str.strip()
    return df


def process_ctd(ctd_dir: Path, out_dir: Path) -> Path | None:
    files = sorted(ctd_dir.glob("ctd_*.csv"))
    logger.info("CTD: %d logger files", len(files))
    frames = []
    for path in files:
        try:
            frames.append(_read_ctd_csv(path))
        except Exception as exc:
            logger.warning("  Skipping %s: %s", path.name, exc)
    if not frames:
        return None

    df = pd.concat(frames, ignore_index=True).rename(columns=CTD_COLUMNS)
    n_read = len(df)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    value_cols = [c for c in CTD_COLUMNS.values() if c != "time"]
    df[value_cols] = df[value_cols].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["time", *value_cols])
    for col, (lo, hi) in CTD_VALID_RANGES.items():
        df = df[df[col].between(lo, hi)]
    df = df.drop_duplicates(subset="time").sort_values("time")
    df = df[(df["time"] >= EK80_START) & (df["time"] <= EK80_END)]
    logger.info("  %d of %d records kept (malformed or out-of-range lines dropped)", len(df), n_read)
    if df.empty:
        return None

    ctd_out = out_dir / "ctd"
    ctd_out.mkdir(parents=True, exist_ok=True)
    full = ctd_out / "munkholmen_ctd_4hz.csv"
    df[["time", *value_cols]].to_csv(full, index=False, date_format="%Y-%m-%dT%H:%M:%S.%fZ")
    minute = df.set_index("time")[value_cols].resample("1min").mean().dropna(how="all")
    minute.round(5).to_csv(ctd_out / "munkholmen_ctd_1min.csv", date_format="%Y-%m-%dT%H:%M:%SZ")
    logger.info("  Wrote %s (%s → %s) and 1-minute means (%d rows)", full,
                df["time"].iloc[0], df["time"].iloc[-1], len(minute))
    return full


def write_ek80_env_params(out_dir: Path, currents_nc: Path | None, ctd_csv: Path | None) -> Path | None:
    """Write per-day environment parameters for the EK80 Sv computation.

    Temperature is the daily mean from the ADCP (the nearest day with data
    where the ADCP has none); salinity is the mean of the CTD record. Both are
    near-surface measurements applied to the whole water column. Pressure is
    the mid-column value and pH the EK80 setting.
    """
    import json

    if currents_nc is None or ctd_csv is None:
        return None
    with xr.open_dataset(currents_nc) as ds:
        temperature = ds["temperature"].to_series()
    daily = temperature.groupby(temperature.index.strftime("%Y-%m-%d")).mean()
    salinity = float(pd.read_csv(ctd_csv)["salinity_PSU"].mean())

    params = {}
    for day in pd.date_range(EK80_START.date(), EK80_END.date(), freq="D").strftime("%Y-%m-%d"):
        source_day = day if day in daily.index else min(
            daily.index, key=lambda d: abs(pd.Timestamp(d) - pd.Timestamp(day))
        )
        params[day] = {
            "temperature": round(float(daily[source_day]), 3),
            "salinity": round(salinity, 3),
            "pressure": round(SEABED_RANGE_M / 2, 1),
            "pH": 8.0,
            "temperature_source": f"ADCP daily mean ({source_day})",
            "salinity_source": "CTD mean, 2026-04-13 06:22–10:49 UTC, ~1.1 dbar",
        }
    out = out_dir / "ek80_env_params.json"
    out.write_text(json.dumps(params, indent=2) + "\n")
    logger.info("  Wrote %s", out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adcp-dir", type=Path, default=Path.home() / "data/raw/adcp")
    parser.add_argument("--ctd-dir", type=Path, default=Path.home() / "data/raw/ctd")
    parser.add_argument("--out-dir", type=Path, default=Path.home() / "data/munkholmen_2026/sensors")
    parser.add_argument("--salinity", type=float, default=29.0,
                        help="Salinity (PSU) for the ADCP echosounder absorption (default: 29, "
                             "the near-surface value measured by the CTD).")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    out_dir = args.out_dir.expanduser()
    currents = process_adcp_currents(args.adcp_dir.expanduser(), out_dir)
    process_adcp_echosounder(args.adcp_dir.expanduser(), out_dir, args.salinity)
    ctd = process_ctd(args.ctd_dir.expanduser(), out_dir)
    write_ek80_env_params(out_dir, currents, ctd)


if __name__ == "__main__":
    main()
