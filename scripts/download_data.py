#!/usr/bin/env python3
"""Download the datasets used by this project into ./data (gitignored).

Datasets (both Open Access on PhysioNet):
  - CGMacros 1.0.0   https://physionet.org/content/cgmacros/1.0.0/   (~628 MB zip)
  - BUT CGM 1.0.0    https://physionet.org/content/but-cgm/1.0.0/    (validation set)

BUT CGM is ~60 GB in full, almost all of it raw ECG/accelerometer signals (.h5).
By default only its CSV files (CGM, meals, activities, sleep, CPET, ...) are
downloaded. Use --include-hr for beat-by-beat heart rate CSVs and
--include-signals for the raw .h5 signals.

For the separate level-three database, run scripts/build_level3_db.py. It uses
iter_cgmacros_csvs() below to stream just the CGMacros CSVs into the new database.

Usage:
  python scripts/download_data.py                 # both datasets (CSV-only for BUT CGM)
  python scripts/download_data.py --only cgmacros
  python scripts/download_data.py --only but-cgm --include-hr
  python scripts/download_data.py --delete-zip    # remove zips after extracting
  python scripts/download_data.py --unzip-only    # just extract zips already in data/
"""

from __future__ import annotations

import argparse
import io
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

CGMACROS_URL = "https://physionet.org/files/cgmacros/1.0.0/CGMacros_dateshifted365.zip"
BUT_CGM_URL = "https://physionet.org/files/but-cgm/1.0.0/"

USER_AGENT = "WHACK-data-downloader/1.0"


def _open(url: str, retries: int = 5, headers: dict[str, str] | None = None):
    """Open url, retrying with backoff on timeouts / transient network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries - 1:
                raise
        time.sleep(2**attempt)


class _RemoteZip(io.RawIOBase):
    """Read selected CGMacros CSVs with byte ranges, without downloading photos."""

    def __init__(self, url: str):
        super().__init__()
        with _open(url, headers={"Range": "bytes=0-0"}) as response:
            if response.status != 206:
                raise RuntimeError("The CGMacros server must support HTTP byte ranges.")
            self.url = response.geturl()
            self.size = int(response.headers["Content-Range"].rsplit("/", 1)[1])
            response.read()
        self.position = 0

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.size + offset
        else:
            raise ValueError("Invalid seek origin.")
        if position < 0:
            raise ValueError("Cannot seek before the start of the archive.")
        self.position = position
        return position

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.position + size, self.size)
        if self.position >= end:
            return b""
        with _open(self.url, headers={"Range": f"bytes={self.position}-{end - 1}"}) as response:
            # Fail before reading the response if the server ignores Range.
            if response.status != 206:
                raise RuntimeError("The CGMacros server must support HTTP byte ranges.")
            content = response.read()
        if len(content) != end - self.position:
            raise RuntimeError("Incomplete CGMacros download; please try again.")
        self.position = end
        return content


def iter_cgmacros_csvs():
    """Yield (source participant ID, CSV bytes) for every available person.

    No ZIP, meal photograph, or intermediate CSV is saved. The level-three builder
    consumes these bytes directly. Both datasets' on-disk download commands below
    remain available independently.
    """
    with _RemoteZip(CGMACROS_URL) as remote, zipfile.ZipFile(remote) as archive:
        files = [
            name for name in archive.namelist()
            if re.search(r"(?:^|/)CGMacros-\d+\.csv$", name) and "__MACOSX" not in name
        ]
        if not files:
            raise ValueError("No participant CSVs found in the CGMacros archive.")
        files.sort(key=lambda name: int(re.search(r"CGMacros-(\d+)\.csv$", name).group(1)))
        for name in files:
            participant_id = int(re.search(r"CGMacros-(\d+)\.csv$", name).group(1))
            yield participant_id, archive.read(name)


def download_file(url: str, dest: Path, show_progress: bool = False) -> None:
    """Download url -> dest, skipping if it already exists. Writes to a .part file first."""
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _open(url) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if show_progress and total:
                print(f"\r  {done / 1e6:7.1f} / {total / 1e6:.1f} MB ({100 * done / total:5.1f}%)", end="", flush=True)
    if show_progress:
        print()
    tmp.rename(dest)


def _marker(zip_path: Path) -> Path:
    return zip_path.with_name(f".{zip_path.name}.extracted")


def extract_zip(zip_path: Path, dest: Path | None = None, delete_zip: bool = False) -> None:
    """Unzip zip_path into dest (default: the zip's folder). Skips if already extracted."""
    dest = dest or zip_path.parent
    marker = _marker(zip_path)
    if marker.exists():
        print(f"  already extracted: {zip_path.name}")
        return
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"{zip_path} is corrupted (first bad member: {bad}); delete it and re-run")
        members = zf.infolist()
        for i, member in enumerate(members, 1):
            zf.extract(member, dest)
            if i % 50 == 0 or i == len(members):
                print(f"\r  extracting {zip_path.name}: {i}/{len(members)} files", end="", flush=True)
    print()
    marker.touch()
    if delete_zip:
        zip_path.unlink()
        print(f"  deleted {zip_path.name}")


def extract_all(root: Path, delete_zip: bool = False) -> None:
    """Unzip every .zip found under root."""
    zips = sorted(root.rglob("*.zip"))
    if not zips:
        print(f"no .zip files found under {root}")
    for z in zips:
        extract_zip(z, delete_zip=delete_zip)


def download_cgmacros(delete_zip: bool = False) -> None:
    target = DATA_DIR / "cgmacros"
    zip_path = target / "CGMacros_dateshifted365.zip"
    if _marker(zip_path).exists():
        print(f"[cgmacros] already downloaded and extracted -> {target}")
        return
    print(f"[cgmacros] downloading {CGMACROS_URL}")
    download_file(CGMACROS_URL, zip_path, show_progress=True)
    print("[cgmacros] extracting...")
    extract_zip(zip_path, target, delete_zip=delete_zip)
    print(f"[cgmacros] done -> {target}")


def list_dir(url: str) -> tuple[list[str], list[str]]:
    """Parse a PhysioNet /files/ directory listing into (subdirs, files)."""
    with _open(url) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    hrefs = {h for h in re.findall(r'href="([^"?#]+)"', html) if not h.startswith(("/", "http", "..", "."))}
    dirs = sorted(h for h in hrefs if h.endswith("/"))
    files = sorted(h for h in hrefs if not h.endswith("/"))
    return dirs, files


def want_but_cgm_file(name: str, include_hr: bool, include_signals: bool) -> bool:
    if name.endswith(".h5"):
        return include_signals
    if name.endswith("_HR.csv"):
        return include_hr
    return True


def download_but_cgm(include_hr: bool, include_signals: bool, workers: int) -> None:
    target = DATA_DIR / "but-cgm"
    print(f"[but-cgm] listing {BUT_CGM_URL}")
    subdirs, top_files = list_dir(BUT_CGM_URL)

    jobs: list[tuple[str, Path]] = [(BUT_CGM_URL + f, target / f) for f in top_files]
    for i, d in enumerate(subdirs, 1):
        print(f"\r[but-cgm] indexing participant folders {i}/{len(subdirs)}", end="", flush=True)
        _, files = list_dir(BUT_CGM_URL + d)
        jobs += [
            (BUT_CGM_URL + d + f, target / d / f)
            for f in files
            if want_but_cgm_file(f, include_hr, include_signals)
        ]
    print()

    todo = [(u, p) for u, p in jobs if not p.exists()]
    print(f"[but-cgm] {len(jobs)} files selected, {len(todo)} to download")
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_file, u, p): u for u, p in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
            except Exception as e:  # keep going; report at the end
                failures += 1
                print(f"\n  failed: {futures[fut]} ({e})")
            print(f"\r[but-cgm] {n}/{len(todo)} downloaded", end="", flush=True)
    print()
    if failures:
        print(f"[but-cgm] {failures} file(s) failed - re-run the script to retry them.")
    print(f"[but-cgm] done -> {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=["cgmacros", "but-cgm"], help="download just one dataset")
    parser.add_argument("--include-hr", action="store_true", help="BUT CGM: include per-day beat-by-beat HR CSVs")
    parser.add_argument(
        "--include-signals", action="store_true", help="BUT CGM: include raw ECG/ACC .h5 files (~60 GB!)"
    )
    parser.add_argument("--workers", type=int, default=8, help="parallel downloads for BUT CGM (default 8)")
    parser.add_argument("--delete-zip", action="store_true", help="delete .zip files after extracting them")
    parser.add_argument(
        "--unzip-only", action="store_true", help="don't download; just extract any .zip files already in data/"
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    if args.unzip_only:
        extract_all(DATA_DIR, delete_zip=args.delete_zip)
        return 0
    if args.include_signals:
        free_gb = shutil.disk_usage(DATA_DIR).free / 1e9
        print(f"WARNING: --include-signals downloads ~60 GB (free disk: {free_gb:.0f} GB).")

    if args.only in (None, "cgmacros"):
        download_cgmacros(delete_zip=args.delete_zip)
    if args.only in (None, "but-cgm"):
        download_but_cgm(args.include_hr, args.include_signals, args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
