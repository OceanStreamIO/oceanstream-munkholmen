# The dataset in the Denoise Lab

The OceanStream Denoise Lab is the web application the products were made with (see [Software](software.md#the-denoise-lab)). The same days are set up in it, so anyone with access to the lab can run the pipeline on a day with other parameters and compare the echograms of every stage with the published run.

## The survey

The survey `munkholmen-2026` ("Munkholmen buoy, April 2026") points at the Azure file share that holds the raw files and carries the processing settings of this dataset, so a lab run reproduces it.

| | |
|---|---|
| Source | The Azure file share; the EK80 `.raw` files grouped by day from their names |
| Pulse categories | `short_pulse` only, so the lab skips the combined long- and short-pulse figure |
| How Sv is computed | 100 m crop, 0.107 m range bins, 32-bit floats, transducer depth 0 m, 250-ping chunks, the measured water properties per day, no GPS track |
| Run defaults | Seabed mask on, from the leading edge, 0.5 m above; surface exclusion 1 m; MVBS 0.5 m × 10 s; cross-talk detector off; Sv clip −10 dB; pruning at 80 % |
| Featured days | 12 April, the most representative day, and 13 April |

The Sv the lab computes for a day matches the published `sv/` store exactly. The published Sv was seeded into the lab's shared Sv container, so a run reuses it ("Skip Sv") unless asked to compute it again.

## The presets

| Preset | Impulse threshold | Transient threshold | Note |
|---|---|---|---|
| `munkholmen-fjord`, "Munkholmen fjord (April 2026)" | 12 dB | 15 dB | `processing/munkholmen_denoise.toml`; the published products |
| `munkholmen-fjord-sensitive`, "Munkholmen fjord, sensitive (trial)" | 8 dB | 6 dB | A trial of more sensitive mask filters; not adopted |

Both can be viewed and exported as TOML or JSON from the Run page; the export of `munkholmen-fjord` is the repository's configuration file.

## What the filters remove

On 13 April, per channel and before and after 11:00 (when full-depth vertical stripes start at 200 kHz), the share of water-column cells (above the seabed mask, below 1 m) that each filter removes:

| | Impulse | Attenuation | Transient | Background | Kept |
|---|---|---|---|---|---|
| 38 kHz, published, before 11:00 | 0.01 % | 0.87 % | 0 % | 44.9 % | 54.2 % |
| 38 kHz, published, after 11:00 | 0.06 % | 0.54 % | 0 % | 46.6 % | 52.8 % |
| 200 kHz, published, before 11:00 | 0.10 % | 0 % | 0 % | 91.4 % | 8.5 % |
| 200 kHz, published, after 11:00 | 0.14 % | 0.08 % | 0 % | 84.1 % | 15.7 % |
| 38 kHz, sensitive, before 11:00 | 0.12 % | 0.87 % | 0.04 % | 44.9 % | 54.1 % |
| 38 kHz, sensitive, after 11:00 | 0.44 % | 0.54 % | 0.05 % | 46.4 % | 52.6 % |
| 200 kHz, sensitive, before 11:00 | 0.26 % | 0 % | 0 % | 91.2 % | 8.5 % |
| 200 kHz, sensitive, after 11:00 | 0.56 % | 0.08 % | 6.24 % | 78.4 % | 14.7 % |

The removals overlap, so the columns do not add up to 100 %. The three mask-based filters remove well under 1 % of the cells; background-noise removal does almost all the work, and at 200 kHz it removes 84–91 % of the water column. The sensitive preset only thins the 200 kHz stripes after 11:00, where its 6 dB transient threshold flags 6.24 % of the cells, and changes nothing else, so the published thresholds stayed.

## Repeating a day

1. Pick the survey and a day in the toolbar and a preset in the Run tab. The Processing options card starts from the survey's run defaults; a thick left edge marks a value changed for this run only.
2. Run. The Sv is reused when the day has it, and computed first otherwise. A day's products step takes about 30 minutes on the lab worker.
3. The Echograms tab shows every stage of the run beside the other runs of that day. The Files tab lists the run's container, `denoise-lab-<preset key>/<day>/`, and the survey's view of the shared Sv.
4. Export the preset as TOML to carry the parameters back into `munkholmen_denoise.toml`.

Whole runs of the script, such as the published one, go through `submit_to_denoise_lab.py`, which starts the lab's batch deployment on the same worker.

## What the lab gained from this dataset

The first survey that was not an open-ocean drone drove several additions to the lab: Sv settings and run defaults per survey (the range crop, the range bins, 32-bit Sv, the transducer depth, the chunking, measured water properties, and the GPS track or none); a seabed mask with a choice of seabed line and offset; pulse categories per survey; a batch deployment that runs a whole script on the worker; and the shared Sv shown per survey in the Files page. They are listed in the [report](report.md#46-what-the-pipeline-and-the-lab-gained).
