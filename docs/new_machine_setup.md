# New Machine Setup — Hyperdirect + Thalamus (Isolated Venv)

## 1) Prereqs
- Python 3.11 or 3.12 available.
- Decide project location, e.g., `~/Projects/Hyperdirect`.

## 2) Get the task code
```bash
git clone <your-Hyperdirect-repo-url> ~/Projects/Hyperdirect
cd ~/Projects/Hyperdirect
```

## 3) Create and activate a private virtualenv
```bash
python3 -m venv venv-thalamus
source venv-thalamus/bin/activate
```
`(venv-thalamus)` should appear in your prompt.

## 4) Install Thalamus **inside this venv**
- Download the matching wheel (e.g., `thalamus-0.3.49-py3-none-any.whl`) from the Thalamus releases page.
```bash
pip install /path/to/thalamus-0.3.49-py3-none-any.whl
```
This installs *into* `venv-thalamus`, leaving any system Thalamus untouched.

## 5) (If needed) Patch Storage2 crash
- Edit `venv-thalamus/lib/python3.*/site-packages/thalamus/servicer.py` to support `match.path.indices[0]` when `.index` is missing (the patch we applied locally). This change lives only in your venv.

## 6) Launch Thalamus with your extension
```bash
cd ~/Projects/Hyperdirect
source venv-thalamus/bin/activate
python -m thalamus.task_controller --ext hyperdirect_thalamus_ext
```

## 7) Configure nodes in the GUI (minimal)
- Add `task_controller` (Node 1).
- Add `Storage2` (Node 2):
  - Sources: Node 1, check **Text** (add Time Series only if needed).
  - Output File: full path to a filename, e.g., `/Users/you/Projects/Hyperdirect/Pilot_Data/raw/session01.tha` (folder must exist).
  - Files table: one row, same path as Output File.
- Click **Running** on Storage2, then **Rec** (rec = 1).
- Click **Running** on task_controller and run the task.

## 8) Hydrate and analyze
```bash
python -m thalamus.hydrate /Users/you/Projects/Hyperdirect/Pilot_Data/raw/session01.tha --out /tmp/hydrated
PYTHONPATH=. python analyze_tha.py --tha /Users/you/Projects/Hyperdirect/Pilot_Data/raw/session01.tha --out-root "/Users/you/Projects/Hyperdirect/Pilot_Data/figures"
```

## 9) Common pitfalls
- Not activating `venv-thalamus` → runs unpatched/system Thalamus, may crash.
- Storage2 Output File blank or pointing to a directory → crash on Running.
- Empty/extra source rows → `Index` AttributeError. Keep one valid row.
- Forgetting to click **Rec** on Storage2 → no `.tha` saved.

## 10) Cleanup
- To remove your isolated install, delete the `venv-thalamus` folder. The system’s Thalamus remains untouched.
