# Hyperdirect STOPGO Task (Thalamus)

## Overview
This repository contains a Thalamus task-controller extension that implements a STOPGO (stop-signal) task modeled after the original MATLAB prototype. It also includes a helper analysis script for quick pilot visualization.

## Repo contents
- `hyperdirect_thalamus_ext/` — Thalamus extension module registering the STOPGO task (`tasks.py`) and the trial logic (`stopgo_task.py`). A smoke test is provided in `_smoke_test_stopgo.py`.
- `analyze_tha.py` — Hydrates a recorded `.tha` file and generates pilot figures (RT histogram, SSD ladders, stop-success by modality).
- `Task Design/STOPGO.m` — Original MATLAB reference implementation.

## How to run the task
**Short version**
1. Install Thalamus (latest release wheel) and ensure it’s on your Python path.
2. From the repo root:  
   ```bash
   PYTHONPATH=. python -m thalamus.task_controller --ext hyperdirect_thalamus_ext
   ```
3. In the UI, select the task “STOPGO (Stop-signal)”, set `goal = ntrials`, wire a `STORAGE2` node to the task controller for Text/Time Series, arm `Running`, then run.

**Long version (step-by-step)**
1. Dependencies  
   - Python 3.10+  
   - Thalamus (install latest release wheel or `pip install thalamus` from source)  
   - Qt dependencies required by Thalamus UI.
2. Launch with extension  
   ```bash
   cd /Users/kamrenkhan/Desktop/Research/RESTORE/Project/Hyperdirect
   PYTHONPATH=. python -m thalamus.task_controller --ext hyperdirect_thalamus_ext
   ```
3. Configure the task in the UI  
   - Task: “STOPGO (Stop-signal)”.  
   - Key params (defaults match MATLAB): `stopFrac=0.36`, `ssdStart=0.300s`, `ssdStep=0.050s`, `ssdMin=0.055s`, `ssdMax=1.0s`, `respWindow=1.5s`, fixation 1.5–2.0s, `ntrials=100`.  
   - GO responses: keyboard `1` and `2`. Stop cues: red “X” (visual) or 3-tone chord (auditory), with independent SSD ladders.
4. Wire storage  
   - Add a `STORAGE2` node, set `Output File` to an absolute path (e.g., `Pilot Data/session01.tha`).  
   - Sources: set `Node` to your task controller node; enable `Text` and `Time Series` (leave Image/Motion off).  
   - Arm `Running` after wiring.
5. Run and monitor  
   - Set `goal = ntrials` so the controller runs the full planned schedule.  
   - Watch the UI states (`stopgo_fixation`, `stopgo_go`, `stopgo_stop_visual`/`audio`, `stopgo_iti`).
6. Quick validation  
   - Optional dry-run: `PYTHONPATH=. python -m hyperdirect_thalamus_ext._smoke_test_stopgo` to sanity-check ladder logic and logging.

## Analyze a recorded session
1. Ensure pandas and matplotlib are installed (`pip install --upgrade --force-reinstall pandas matplotlib` if needed).  
2. Run:  
   ```bash
   PYTHONPATH=. python analyze_tha.py \
     --tha /path/to/session.tha \
     --out-root "Pilot Data/figures"
   ```
3. Outputs: PNGs in `Pilot Data/figures/<session>/` for RT histogram, SSD ladder trajectories, and stop-success rates by modality.

## Tips for piloting
- Use a short pilot block (`ntrials=10`, `stopFrac=0.5`, `reset_schedule=True`) to verify both stop modalities.  
- Confirm audio output is routed correctly before the first auditory stop trial (tone file is generated lazily).  
- Keep `Running` unchecked until the storage node has a valid output path and source wiring to avoid crashes.
