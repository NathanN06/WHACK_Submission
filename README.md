# WHACK_Submission

**An AI researcher that tests its own ideas — and can tell a real discovery from a lucky one.**

Finding patterns in data is easy; knowing which ones to trust is hard. This project generates hypotheses from a dataset (markets, sport, medicine, online experiments…), then stress-tests each one before calling it a discovery.

## Structure

```
backend/    API + research/statistics engine
frontend/   Web UI
docs/       Notes, design, pitch material
scripts/    Utility scripts (e.g. dataset download)
data/       Downloaded datasets (gitignored, not committed)
```

## Data

We use two open-access continuous glucose monitoring (CGM) datasets from PhysioNet:

| Dataset | Role | What's in it |
|---|---|---|
| [CGMacros 1.0.0](https://physionet.org/content/cgmacros/1.0.0/) | Main dataset | CGM readings, meal macronutrients, meal photos and activity data |
| [BUT CGM 1.0.0](https://physionet.org/content/but-cgm/1.0.0/) | Validation | 60 healthy, active adults over ~10 days: CGM, meals, activities, sleep, steps, CPET (lab exercise tests), questionnaires |

Download both into `data/` (needs Python 3.9+, no extra packages):

```bash
python3 scripts/download_data.py
```

| Command | Downloads |
|---|---|
| `python3 scripts/download_data.py` | CGMacros (~628 MB zip, extracted) and BUT CGM CSV files only |
| `python3 scripts/download_data.py --only cgmacros` | CGMacros only |
| `python3 scripts/download_data.py --only but-cgm` | BUT CGM only |
| `python3 scripts/download_data.py --include-hr` | Also BUT CGM beat-by-beat heart rate CSVs |
| `python3 scripts/download_data.py --include-signals` | Also BUT CGM raw ECG/accelerometer `.h5` files (**~60 GB**) |
| `python3 scripts/download_data.py --delete-zip` | Delete the CGMacros zip after extracting it (saves ~650 MB) |
| `python3 scripts/download_data.py --unzip-only` | Don't download, just extract any `.zip` already in `data/` |

Re-running the script only fetches files that are missing, so it's safe to run again if a download fails.

Resulting layout:

```
data/
  cgmacros/   CGMacros (zip + extracted files)
  but-cgm/    BUT CGM: top-level CSVs + one folder per participant/session (e.g. 101001/)
```

## Getting started

_Setup instructions coming soon._
