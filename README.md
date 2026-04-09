# Hyperdirect Thalamus Tasks (STOPGO + STOP/GO/SWITCH v2)

## Overview
This repo provides Thalamus task-controller extensions for intraoperative action-control tasks and quick pilot analysis utilities. It now includes the protocol v1.1 STOP/GO/SWITCH task (visual and auditory contexts with control miniblocks) in addition to the original STOPGO task.

## Repo contents
- `hyperdirect_thalamus_ext/` — Extension module registering tasks via `tasks.py`:
  - `stopgo_task.py` (STOPGO) and `_smoke_test_stopgo.py`
  - `stopgoswitch_task.py` (protocol v1.1 STOP/GO/SWITCH with control miniblocks)
- `Task Design/STOPGO.m` — Original MATLAB prototype.
- `Task Design/STN_StopGoSwitch_v2.m` — MATLAB version of the protocol v1.1 STOP/GO/SWITCH task.
- `Task Design/stn_stop_go_switch_protocol_updated.pdf` — Protocol reference.
- `analyze_tha.py` — Hydrates a `.tha` and plots STOPGO pilot figures (RT, SSD ladders, stop success). Use hydrated JSONL for STOP/GO/SWITCH v2 (log key `stopgoswitch_v2_trial`).

## How to run (both tasks)
**Short version**
1. Install Thalamus (latest release wheel) and have it on your Python path.
2. From repo root:
   ```bash
   PYTHONPATH=. python -m thalamus.task_controller --ext hyperdirect_thalamus_ext
   ```
3. In the UI, pick the task:
   - “STOPGO (Stop-signal)” (keys `1`/`2`)
   - “STOP/GO/SWITCH v2 (visual/auditory)” (default keys `Q`/`P`, editable in the UI)
4. Set `goal = ntrials`, wire a `STORAGE2` node (Text + Time Series) with an absolute output path, arm `Running`, then start.

**Long version / safety checklist**
1) Dependencies  
   - Python 3.10+; Thalamus installed; Qt runtime available.
2) Launch with extension  
   ```bash
   cd /Users/kamrenkhan/Desktop/Research/RESTORE/Project/Hyperdirect
   PYTHONPATH=. python -m thalamus.task_controller --ext hyperdirect_thalamus_ext
   ```
3) Task configuration  
   - STOPGO defaults: `stopFrac=0.36`, `ssdStart=0.300`, `ssdStep=0.050`, `ssdMin=0.055`, `ssdMax=1.0`, `respWindow=1.5`, fixation 1.5–2.0 s, `ntrials=100`; keys `1`/`2`.  
   - STOP/GO/SWITCH v2 key parameters (protocol v1.1): block counts per modality = 60 GO / 20 STOP / 20 SWITCH, plus control miniblock (STOP-ignore & SWITCH-ignore). Independent ladders (STOP and SWITCH × modality) start 0.200 s, step 0.050 s, clamp [0.050, 0.900]. Fixation 500–700 ms; movement-cue 500–700 ms; cue duration 150 ms; response window 1500 ms from GO. Default keys Q (left) / P (right); change via UI fields “Left key” / “Right key.”
4) Storage wiring (to avoid crashes)  
   - Add `STORAGE2`, set `Output File` to an absolute writable path (e.g., `Pilot Data/session01.tha`).  
   - Sources: set `Node` to the task controller; enable `Text` and `Time Series`; leave Image/Motion off.  
   - Arm `Running` only after wiring and path are set.
5) Run and monitor  
   - Goal = total trials for the block.  
   - Watch state messages (e.g., `go`, `stop`, `switch`, `iti`) and confirm keypresses register.
6) Quick validation  
   - STOPGO: `PYTHONPATH=. python -m hyperdirect_thalamus_ext._smoke_test_stopgo` (no hardware).  
   - STOP/GO/SWITCH: run a short pilot block (e.g., 10 trials) with `goal=10` to verify cues and key mapping.

## Analyze recorded sessions (STOPGO + STOP/GO/SWITCH v2)
`analyze_tha.py` now understands both schemas (`stopgo_trial` and `stopgoswitch_v2_trial`), reading directly from the hydrated H5.

Recommended headless invocation (avoids macOS GUI backend issues):
```bash
cd /Users/kamrenkhan/Desktop/Research/RESTORE/Project/Hyperdirect
source ../Thalamus/venv-thalamus/bin/activate   # ensure patched Thalamus env
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/mplconfig PYTHONPATH=. \
python analyze_tha.py --tha /path/to/session.tha --out-root "Pilot Data/figures"
```
Outputs in `Pilot Data/figures/<session>/`:
- `rt_hist.png`
- `ssd_ladders.png` (auto-detects SSD column names for either task)
- `timeline.png` (trial # vs trial_type, color-coded by success)
- `stop_success.png`
- `summary.txt` (trial count, approximate duration, overall accuracy)

## Tips for piloting
- Start with a short block (e.g., 10 trials) to confirm audio routing and key mapping.  
- Keep `Running` unchecked until the storage node has a valid path and sources.  
- For auditory blocks, verify system audio output before the first STOP/SWITCH cue.  
- Use absolute paths for output to avoid HDF5 “is a directory” errors.
