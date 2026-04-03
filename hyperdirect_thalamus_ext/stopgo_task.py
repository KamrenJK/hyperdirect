"""
STOPGO stop-signal task implemented as a Thalamus Task Controller task.

Behavior mirrors Hyperdirect/Task Design/STOPGO.m:
- GO cue is digit 1 or 2
- Subject responds with keyboard 1/2 within respWindow
- Stop trials deliver either visual STOP (X) or auditory STOP (tone) after SSD
- Visual and auditory stop modalities each have independent SSD staircases
"""

from __future__ import annotations

import asyncio
import datetime
import json
import math
import random
import tempfile
import time
import typing
import wave

import numpy as np

from thalamus.qt import QFont, QColor, QPainter, QRect, Qt, QSound, QWidget, QVBoxLayout
from thalamus.task_controller.widgets import Form
from thalamus.task_controller.util import animate, wait_for, TaskResult
from thalamus import task_controller_pb2
from thalamus.config import ObservableCollection

LOGGER_NAME = __name__


RANDOM_DEFAULT = {"min": 1, "max": 1}

STOP_VIS = 1
STOP_AUD = 2


class Config(typing.NamedTuple):
    fix_min_s: float
    fix_max_s: float
    resp_window_s: float
    iti_s: float
    stop_frac: float
    ntrials: int
    ssd_start_s: float
    ssd_step_s: float
    ssd_min_s: float
    ssd_max_s: float
    go_text_size: int
    stop_text_size: int
    fixation_char: str
    stop_char: str
    stop_color: typing.List[int]
    tone_duration_s: float


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _get_or_init(task_config: ObservableCollection, key: str, default: typing.Any) -> typing.Any:
    if key not in task_config:
        task_config[key] = default
    return task_config[key]


def _ensure_schedule(task_config: ObservableCollection, cfg: Config) -> None:
    """
    Ensure trial schedules exist in task_config and match cfg.ntrials.
    Schedules are persisted so running the task for goal=N executes deterministic
    trials for that config snapshot.
    """
    schedule_seed = int(_get_or_init(task_config, "schedule_seed", int(time.time())))
    current_ntrials = int(_get_or_init(task_config, "ntrials", cfg.ntrials))

    # If user changed ntrials in UI, regenerate schedule.
    if current_ntrials != cfg.ntrials:
        task_config["ntrials"] = int(cfg.ntrials)
        task_config["trial_index"] = 0
        for k in ("isStop", "goInstr", "stopType", "fixLag"):
            if k in task_config:
                del task_config[k]

    if "trial_index" not in task_config:
        task_config["trial_index"] = 0

    if all(k in task_config for k in ("isStop", "goInstr", "stopType", "fixLag")):
        # already generated
        return

    rng = random.Random(schedule_seed)

    is_stop = [rng.random() < cfg.stop_frac for _ in range(cfg.ntrials)]

    # Balance auditory vs visual within stop trials.
    stop_indices = [i for i, v in enumerate(is_stop) if v]
    n_stop = len(stop_indices)
    tmp = [STOP_VIS] * math.ceil(n_stop / 2) + [STOP_AUD] * math.floor(n_stop / 2)
    rng.shuffle(tmp)

    stop_type = [0] * cfg.ntrials
    for j, idx in enumerate(stop_indices):
        stop_type[idx] = tmp[j]

    go_instr = [rng.randint(1, 2) for _ in range(cfg.ntrials)]
    fix_lag = [rng.uniform(cfg.fix_min_s, cfg.fix_max_s) for _ in range(cfg.ntrials)]

    task_config["isStop"] = is_stop
    task_config["goInstr"] = go_instr
    task_config["stopType"] = stop_type
    task_config["fixLag"] = fix_lag


def _tone_wav_path(cfg: Config) -> str:
    # deterministic-ish by duration to avoid repeated writes for same params
    return str(
        (tempfile.gettempdir())
        + f"/thalamus_stopgo_tone_{int(cfg.tone_duration_s * 1000)}ms.wav"
    )


def _ensure_tone_wav(cfg: Config) -> str:
    """
    Create a small WAV file for the auditory stop cue if it doesn't exist.
    Uses the same 3-tone chord as STOPGO.m (900, 1370, 2130 Hz).
    """
    path = _tone_wav_path(cfg)
    try:
        with open(path, "rb"):
            return path
    except OSError:
        pass

    fs = 44100
    t = np.arange(int(fs * cfg.tone_duration_s)) / fs
    tone = (
        np.sin(2 * np.pi * 900 * t)
        + np.sin(2 * np.pi * 1370 * t)
        + np.sin(2 * np.pi * 2130 * t)
    )
    tone = tone / np.max(np.abs(tone))
    tone = tone * 0.75
    pcm = (tone * 32767.0).astype(np.int16)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(pcm.tobytes())

    return path


def create_widget(task_config: ObservableCollection) -> QWidget:
    result = QWidget()
    layout = QVBoxLayout()
    result.setLayout(layout)

    # Core timing + staircase parameters.
    form = Form.build(
        task_config,
        ["Name:", "Value:"],
        Form.Constant("Trials (ntrials)", "ntrials", 100),
        Form.Constant("Stop fraction", "stopFrac", 0.36, precision=3),
        Form.Constant("Fix min", "fixMin", 1.5, "s", precision=3),
        Form.Constant("Fix max", "fixMax", 2.0, "s", precision=3),
        Form.Constant("Response window", "respWindow", 1.5, "s", precision=3),
        Form.Constant("Inter-trial interval", "iti", 0.3, "s", precision=3),
        Form.Constant("SSD start", "ssdStart", 0.300, "s", precision=3),
        Form.Constant("SSD step", "ssdStep", 0.050, "s", precision=3),
        Form.Constant("SSD min", "ssdMin", 0.055, "s", precision=3),
        Form.Constant("SSD max", "ssdMax", 1.000, "s", precision=3),
        Form.Constant("GO text size", "goTextSize", 120, precision=0),
        Form.Constant("STOP text size", "stopTextSize", 150, precision=0),
        Form.String("Fixation char", "fixationChar", "+"),
        Form.String("STOP char", "stopChar", "X"),
        Form.Color("STOP color", "stopColor", QColor(255, 0, 0)),
        Form.Constant("Tone duration", "toneDuration", 0.15, "s", precision=3),
        Form.Constant("Schedule seed", "schedule_seed", int(time.time()), precision=0),
        Form.Bool("Reset schedules on next trial", "reset_schedule", False),
    )
    layout.addWidget(form)

    return result


def _read_config(task_config: ObservableCollection) -> Config:
    stop_color = task_config.get("stopColor", [255, 0, 0])
    if isinstance(stop_color, ObservableCollection):
        stop_color = list(stop_color)
    return Config(
        fix_min_s=float(task_config.get("fixMin", 1.5)),
        fix_max_s=float(task_config.get("fixMax", 2.0)),
        resp_window_s=float(task_config.get("respWindow", 1.5)),
        iti_s=float(task_config.get("iti", 0.3)),
        stop_frac=float(task_config.get("stopFrac", 0.36)),
        ntrials=int(task_config.get("ntrials", 100)),
        ssd_start_s=float(task_config.get("ssdStart", 0.300)),
        ssd_step_s=float(task_config.get("ssdStep", 0.050)),
        ssd_min_s=float(task_config.get("ssdMin", 0.055)),
        ssd_max_s=float(task_config.get("ssdMax", 1.000)),
        go_text_size=int(task_config.get("goTextSize", 120)),
        stop_text_size=int(task_config.get("stopTextSize", 150)),
        fixation_char=str(task_config.get("fixationChar", "+")),
        stop_char=str(task_config.get("stopChar", "X")),
        stop_color=[int(stop_color[0]), int(stop_color[1]), int(stop_color[2])],
        tone_duration_s=float(task_config.get("toneDuration", 0.15)),
    )


def _make_text_renderer(
    *,
    context_widget: QWidget,
    text: str,
    size: int,
    color: QColor,
) -> typing.Callable[[QPainter], None]:
    def renderer(p: QPainter) -> None:
        p.setPen(color)
        p.setFont(QFont("Arial", int(size)))
        rect = QRect(0, 0, context_widget.width(), context_widget.height())
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

    return renderer


@animate(60)
async def run(context) -> TaskResult:
    """
    Executes exactly one STOPGO trial. Schedules and staircase state are stored in task_config
    so they persist across trials (goal should be set to ntrials).
    """
    assert context.widget is not None, "STOPGO requires a canvas (non-remote executor mode)"

    task_config = context.task_config
    cfg = _read_config(task_config)

    if task_config.get("reset_schedule", False):
        task_config["reset_schedule"] = False
        task_config["trial_index"] = 0
        for k in ("isStop", "goInstr", "stopType", "fixLag"):
            if k in task_config:
                del task_config[k]

    _ensure_schedule(task_config, cfg)

    # Persistent independent ladders.
    ssd_vis = float(_get_or_init(task_config, "ssd_vis", cfg.ssd_start_s))
    ssd_aud = float(_get_or_init(task_config, "ssd_aud", cfg.ssd_start_s))

    tr = int(_get_or_init(task_config, "trial_index", 0))
    if tr >= cfg.ntrials:
        # Already done all planned trials; succeed without doing anything.
        await context.servicer.publish_state(task_controller_pb2.BehavState(state="stopgo_done"))
        return TaskResult(True)

    is_stop = bool(task_config["isStop"][tr])
    go_instr = int(task_config["goInstr"][tr])
    stop_type = int(task_config["stopType"][tr]) if is_stop else 0
    fix_lag_s = float(task_config["fixLag"][tr])

    # Snapshot ladder values at start of trial (matches MATLAB ssdVisOverTime/ssdAudOverTime behavior).
    ssd_vis_snapshot = ssd_vis
    ssd_aud_snapshot = ssd_aud

    # Choose SSD for this trial.
    ssd_used = None
    if is_stop:
        ssd_used = ssd_vis if stop_type == STOP_VIS else ssd_aud

    # Key handling (capture first 1/2 press, store timestamp).
    response_value: typing.Optional[int] = None
    response_time_perf: typing.Optional[float] = None

    def key_handler(e) -> None:
        nonlocal response_value, response_time_perf
        try:
            k = e.key()
        except Exception:
            return

        if response_value is not None:
            return

        if k == Qt.Key.Key_1:
            response_value = 1
            response_time_perf = time.perf_counter()
        elif k == Qt.Key.Key_2:
            response_value = 2
            response_time_perf = time.perf_counter()

        if response_value is not None:
            context.process()

    context.widget.key_release_handler = key_handler

    # Audio setup (create tone file lazily).
    tone_path = _ensure_tone_wav(cfg) if is_stop and stop_type == STOP_AUD else None
    tone_sound = QSound(tone_path) if tone_path else None

    # Trial: fixation
    await context.servicer.publish_state(task_controller_pb2.BehavState(state="stopgo_fixation"))
    context.widget.renderer = _make_text_renderer(
        context_widget=context.widget,
        text=cfg.fixation_char,
        size=cfg.go_text_size,
        color=QColor(255, 255, 255),
    )
    context.widget.update()
    await context.sleep(datetime.timedelta(seconds=fix_lag_s))

    # Trial: GO
    await context.servicer.publish_state(task_controller_pb2.BehavState(state="stopgo_go"))
    context.widget.renderer = _make_text_renderer(
        context_widget=context.widget,
        text=str(go_instr),
        size=cfg.go_text_size,
        color=QColor(255, 255, 255),
    )
    context.widget.update()
    go_on_perf = time.perf_counter()

    # Schedule STOP delivery (best-effort, event-loop based timing).
    stop_delivered = False
    stop_on_perf: typing.Optional[float] = None

    async def deliver_stop() -> None:
        nonlocal stop_delivered, stop_on_perf
        if not is_stop or ssd_used is None:
            return
        await context.sleep(datetime.timedelta(seconds=float(ssd_used)))
        if stop_type == STOP_VIS:
            await context.servicer.publish_state(task_controller_pb2.BehavState(state="stopgo_stop_visual"))
            context.widget.renderer = _make_text_renderer(
                context_widget=context.widget,
                text=cfg.stop_char,
                size=cfg.stop_text_size,
                color=QColor(int(cfg.stop_color[0]), int(cfg.stop_color[1]), int(cfg.stop_color[2])),
            )
            context.widget.update()
            stop_on_perf = time.perf_counter()
        else:
            await context.servicer.publish_state(task_controller_pb2.BehavState(state="stopgo_stop_audio"))
            stop_on_perf = time.perf_counter()
            if tone_sound:
                tone_sound.play()
        stop_delivered = True

    stop_task = asyncio.get_event_loop().create_task(deliver_stop())

    # Response window: wait for response OR timeout.
    resp_deadline = datetime.timedelta(seconds=cfg.resp_window_s)
    responded = await wait_for(context, lambda: response_value is not None, resp_deadline)
    if not stop_task.done():
        # keep stop cue delivery for accurate stop-on timestamp if it happens before window end
        try:
            await asyncio.wait_for(stop_task, timeout=0.0)
        except Exception:
            pass

    rt_s = None
    if responded and response_time_perf is not None:
        rt_s = float(response_time_perf - go_on_perf)

    # Stop success definition for stop trials.
    stop_success = None
    if is_stop:
        stop_success = (response_value is None)

        # Update the correct ladder only.
        if stop_type == STOP_VIS:
            if stop_success:
                ssd_vis = _clamp(ssd_vis + cfg.ssd_step_s, cfg.ssd_min_s, cfg.ssd_max_s)
            else:
                ssd_vis = _clamp(ssd_vis - cfg.ssd_step_s, cfg.ssd_min_s, cfg.ssd_max_s)
        elif stop_type == STOP_AUD:
            if stop_success:
                ssd_aud = _clamp(ssd_aud + cfg.ssd_step_s, cfg.ssd_min_s, cfg.ssd_max_s)
            else:
                ssd_aud = _clamp(ssd_aud - cfg.ssd_step_s, cfg.ssd_min_s, cfg.ssd_max_s)

        task_config["ssd_vis"] = float(ssd_vis)
        task_config["ssd_aud"] = float(ssd_aud)

    # Inter-trial interval (blank).
    await context.servicer.publish_state(task_controller_pb2.BehavState(state="stopgo_iti"))
    context.widget.renderer = lambda p: None
    context.widget.update()
    await context.sleep(datetime.timedelta(seconds=cfg.iti_s))

    # Persist trial index.
    task_config["trial_index"] = int(tr + 1)

    # Trial log payload.
    trial_result = {
        "trial_index": tr,
        "ntrials": cfg.ntrials,
        "isStop": is_stop,
        "stopType": stop_type if is_stop else None,
        "goInstr": go_instr,
        "fixLag": fix_lag_s,
        "ssdUsed": float(ssd_used) if ssd_used is not None else None,
        "ssdVisStart": float(ssd_vis_snapshot),
        "ssdAudStart": float(ssd_aud_snapshot),
        "ssdVisEnd": float(ssd_vis),
        "ssdAudEnd": float(ssd_aud),
        "goOn_perf_counter_s": float(go_on_perf),
        "stopOn_perf_counter_s": float(stop_on_perf) if stop_on_perf is not None else None,
        "resp": int(response_value) if response_value is not None else None,
        "rt": float(rt_s) if rt_s is not None else None,
        "stopSuccess": bool(stop_success) if stop_success is not None else None,
        "stopDelivered": bool(stop_delivered) if is_stop else None,
    }

    context.behav_result = trial_result
    await context.log(json.dumps({"stopgo_trial": trial_result}))

    # Always return success=True so goal decrements regardless of trial outcome.
    return TaskResult(True)

