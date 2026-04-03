"""
Quick analysis and figure export for Thalamus STOPGO sessions.

Usage:
  python analyze_tha.py --tha /path/to/session.tha --out-root "Pilot Data/figures"

What it does:
  1) Runs Thalamus hydrate on the .tha (to a temp folder).
  2) Scans hydrated jsonl logs for STOPGO trial records ("stopgo_trial").
  3) Builds a few pilot-ready plots:
       - RT histogram (go trials + failed stops).
       - SSD ladder trajectories (visual vs auditory).
       - Stop‑success rate by modality.
  4) Saves PNGs into <out-root>/<session-name>/.

Dependencies: thalamus (for hydrate), pandas, matplotlib.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List


def _ensure_deps():
    try:
        import pandas  # noqa: F401
        import matplotlib  # noqa: F401
    except Exception as exc:  # pragma: no cover - quick guard
        raise SystemExit(
            "pandas/matplotlib import failed. Fix your env (e.g., pip install --upgrade --force-reinstall pandas matplotlib)"
        ) from exc


def _hydrate(tha_path: Path, dest: Path) -> None:
    """
    Run hydrate, writing to a concrete file path (not a directory).
    Thalamus hydrate expects --out to be the output H5 filename.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python",
        "-m",
        "thalamus.hydrate",
        str(tha_path),
        "--out",
        str(dest),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(
            f"Hydrate failed (status {res.returncode}). Stdout:\n{res.stdout}\nStderr:\n{res.stderr}"
        )


def _collect_trials(hydrated_dir: Path) -> List[dict]:
    trials: List[dict] = []
    for path in hydrated_dir.rglob("*.jsonl"):
        with path.open() as f:
            for line in f:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Log lines are expected to be {"stopgo_trial": {...}}
                if "stopgo_trial" in payload:
                    trials.append(payload["stopgo_trial"])
    return trials


def _make_figures(trials: List[dict], out_dir: Path, session_name: str) -> None:
    import pandas as pd
    import matplotlib.pyplot as plt

    if not trials:
        raise SystemExit("No STOPGO trial records found after hydrate.")

    df = pd.DataFrame(trials)

    # RT histogram (only trials with a response)
    rt_df = df[df["rt"].notna()]
    plt.figure(figsize=(6, 4))
    plt.hist(rt_df["rt"], bins=20, color="#4C72B0", edgecolor="black")
    plt.xlabel("Reaction time (s)")
    plt.ylabel("Count")
    plt.title(f"RT distribution — {session_name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_dir / "rt_hist.png", dpi=150)
    plt.close()

    # SSD trajectories
    plt.figure(figsize=(7, 4))
    plt.plot(df.index, df["ssdVisEnd"], label="SSD visual", color="#DD8452")
    plt.plot(df.index, df["ssdAudEnd"], label="SSD auditory", color="#55A868")
    plt.xlabel("Trial")
    plt.ylabel("SSD (s)")
    plt.title(f"SSD ladders — {session_name}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "ssd_ladders.png", dpi=150)
    plt.close()

    # Stop success rate by modality
    stop_df = df[df["isStop"] == True]  # noqa: E712
    if not stop_df.empty:
        # Map 1->VIS, 2->AUD
        stop_df = stop_df.assign(
            modality=stop_df["stopType"].map({1: "visual", 2: "auditory"})
        )
        rates = stop_df.groupby("modality")["stopSuccess"].mean()
        plt.figure(figsize=(4, 4))
        plt.bar(rates.index, rates.values, color=["#DD8452", "#55A868"], edgecolor="black")
        plt.ylim(0, 1)
        plt.ylabel("Stop success rate")
        plt.title(f"Stop success — {session_name}")
        plt.tight_layout()
        plt.savefig(out_dir / "stop_success.png", dpi=150)
        plt.close()


def main():
    _ensure_deps()

    parser = argparse.ArgumentParser(description="Hydrate and plot STOPGO Thalamus session")
    parser.add_argument("--tha", required=True, help="Path to .tha or .tha.json file")
    parser.add_argument(
        "--out-root",
        default="Pilot Data/figures",
        help="Root folder where figures will be saved (session subfolder is added)",
    )
    args = parser.parse_args()

    tha_path = Path(args.tha).expanduser().resolve()
    if tha_path.suffix == ".json":
        tha_path = tha_path.with_suffix("")  # drop .json if user passed manifest

    if not tha_path.exists():
        raise SystemExit(f"Input not found: {tha_path}")

    session_name = tha_path.stem
    out_dir = Path(args.out_root).expanduser().resolve() / session_name

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        out_h5 = tmpdir / "hydrated.h5"
        _hydrate(tha_path, out_h5)
        # Hydrate typically drops auxiliary jsonl/log files alongside the H5 or in the same folder.
        trials = _collect_trials(tmpdir)
        _make_figures(trials, out_dir, session_name)

    print(f"Saved figures to {out_dir}")


if __name__ == "__main__":
    main()
