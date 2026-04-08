"""
STOP/GO/SWITCH task (protocol v1.1) with visual and auditory contexts plus control miniblocks.

Implements:
 - Blocks: visual_active (60 GO, 20 STOP, 20 SWITCH) -> visual_control (8 STOP-ignore, 7 SWITCH-ignore)
            auditory_active (60 GO, 20 STOP, 20 SWITCH) -> auditory_control (7 STOP-ignore, 8 SWITCH-ignore)
 - Four independent staircases: SSD_vis_stop, SSD_vis_switch, SSD_aud_stop, SSD_aud_switch
   start 0.200s, step 0.050s, clamp [0.050, 0.900]
 - Timings: fixation 500-700 ms; movement cue (arrow) 500-700 ms; GO cue onset starts 1500 ms response window
   STOP/SWITCH cues appear after ladder delay; cue duration 150 ms.
 - Responses: left = key 1, right = key 2. SWITCH requires opposite response to the instructed arrow.
 - Control blocks: cues appear but should be ignored; ladders do not update on control trials.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import math
import random
import tempfile
import typing
import wave

import numpy as np

from thalamus.qt import QColor, QFont, QPainter, QRect, Qt, QSound, QWidget, QVBoxLayout
from thalamus.task_controller.widgets import Form
from thalamus.task_controller.util import animate, wait_for, TaskResult
from thalamus import task_controller_pb2
from thalamus.config import ObservableCollection

KEY_MAP = {
    "1": Qt.Key.Key_1,
    "2": Qt.Key.Key_2,
    "q": Qt.Key.Key_Q,
    "p": Qt.Key.Key_P,
}


class Config(typing.NamedTuple):
    block_order: str  # "visual_first" or "auditory_first"
    step_s: float
    delay_min_s: float
    delay_max_s: float
    resp_window_s: float
    cue_duration_s: float
    fixation_min_s: float
    fixation_max_s: float
    move_min_s: float
    move_max_s: float
    iti_s: float
    go_circle_radius_px: int
    text_size: int
    key_left: str
    key_right: str


def create_widget(task_config: ObservableCollection) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout()
    w.setLayout(layout)
    form = Form.build(
        task_config,
        ["Name:", "Value:"],
        # Use a simple string field to avoid combo-box rendering issues on some Qt builds.
        Form.String("Block order (visual_first | auditory_first)", "block_order", "visual_first"),
        Form.Constant("Step size", "step_s", 0.050, "s", precision=3),
        Form.Constant("Delay min", "delay_min_s", 0.050, "s", precision=3),
        Form.Constant("Delay max", "delay_max_s", 0.900, "s", precision=3),
        Form.Constant("Resp window", "resp_window_s", 1.500, "s", precision=3),
        Form.Constant("Cue duration", "cue_duration_s", 0.150, "s", precision=3),
        Form.Constant("Fix min", "fixation_min_s", 0.500, "s", precision=3),
        Form.Constant("Fix max", "fixation_max_s", 0.700, "s", precision=3),
        Form.Constant("Move min", "move_min_s", 0.500, "s", precision=3),
        Form.Constant("Move max", "move_max_s", 0.700, "s", precision=3),
        Form.Constant("ITI", "iti_s", 0.300, "s", precision=3),
        Form.Constant("GO circle radius", "go_radius_px", 120, precision=0),
        Form.Constant("Text size", "text_size", 140, precision=0),
        Form.String("Left key", "key_left", "q"),
        Form.String("Right key", "key_right", "p"),
    )
    layout.addWidget(form)
    return w


def _read_cfg(task_config: ObservableCollection) -> Config:
    return Config(
        block_order=str(task_config.get("block_order", "visual_first")),
        step_s=float(task_config.get("step_s", 0.050)),
        delay_min_s=float(task_config.get("delay_min_s", 0.050)),
        delay_max_s=float(task_config.get("delay_max_s", 0.900)),
        resp_window_s=float(task_config.get("resp_window_s", 1.500)),
        cue_duration_s=float(task_config.get("cue_duration_s", 0.150)),
        fixation_min_s=float(task_config.get("fixation_min_s", 0.500)),
        fixation_max_s=float(task_config.get("fixation_max_s", 0.700)),
        move_min_s=float(task_config.get("move_min_s", 0.500)),
        move_max_s=float(task_config.get("move_max_s", 0.700)),
        iti_s=float(task_config.get("iti_s", 0.300)),
        go_circle_radius_px=int(task_config.get("go_radius_px", 120)),
        text_size=int(task_config.get("text_size", 140)),
        key_left=str(task_config.get("key_left", "q")),
        key_right=str(task_config.get("key_right", "p")),
    )


# Trial representation
class Trial(typing.TypedDict):
    block: str
    context: str  # visual or auditory
    trial_type: str  # go, stop, switch, stop_ignore, switch_ignore
    arrow_dir: str  # left/right
    delay_s: float
    is_control: bool


def _build_block(context: str, active: bool) -> typing.List[Trial]:
    if active:
        types = ["go"] * 60 + ["stop"] * 20 + ["switch"] * 20
        block_name = f"{context}_active"
    else:
        stop_n = 8 if context == "visual" else 7
        switch_n = 7 if context == "visual" else 8
        types = ["stop_ignore"] * stop_n + ["switch_ignore"] * switch_n
        block_name = f"{context}_control"
    random.shuffle(types)
    trials: typing.List[Trial] = []
    for t in types:
        trials.append(
            Trial(
                block=block_name,
                context=context,
                trial_type=t,
                arrow_dir=random.choice(["left", "right"]),
                delay_s=0.200,  # placeholder; overwritten per ladder at runtime
                is_control=not active,
            )
        )
    return trials


def _build_schedule(block_order: str) -> typing.List[Trial]:
    seq = ["visual", "auditory"] if block_order == "visual_first" else ["auditory", "visual"]
    schedule: typing.List[Trial] = []
    for ctx in seq:
        schedule.extend(_build_block(ctx, active=True))
        schedule.extend(_build_block(ctx, active=False))
    return schedule


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _tone_path(freq: int) -> str:
    return str(tempfile.gettempdir() + f"/stopgoswitch_{freq}.wav")


def _ensure_tone(freq: int, duration_s: float = 0.150) -> str:
    path = _tone_path(freq)
    try:
        with open(path, "rb"):
            return path
    except OSError:
        pass
    fs = 44100
    t = np.arange(int(fs * duration_s)) / fs
    tone = np.sin(2 * np.pi * freq * t)
    tone = 0.7 * tone / np.max(np.abs(tone))
    pcm = (tone * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(pcm.tobytes())
    return path


def _make_text_renderer(widget: QWidget, text: str, size: int, color: QColor) -> typing.Callable[[QPainter], None]:
    def render(p: QPainter) -> None:
        p.setPen(color)
        p.setFont(QFont("Arial", int(size)))
        rect = QRect(0, 0, widget.width(), widget.height())
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
    return render


def _make_circle_renderer(widget: QWidget, radius_px: int, color: QColor) -> typing.Callable[[QPainter], None]:
    def render(p: QPainter) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        cx, cy = widget.width() / 2, widget.height() / 2
        r = radius_px
        rect = QRect(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
        p.drawEllipse(rect)
    return render


def _eval_switch_success(arrow_dir: str, resp: typing.Optional[int]) -> typing.Optional[bool]:
    if resp is None:
        return False
    if arrow_dir == "left":
        return resp == 2
    return resp == 1


@animate(60)
async def run(context) -> TaskResult:
    assert context.widget is not None, "Requires canvas (non-remote)"
    cfg = _read_cfg(context.task_config)

    # Staircases
    ssd = {"visual": 0.200, "auditory": 0.200}
    swsd = {"visual": 0.200, "auditory": 0.200}

    schedule = _build_schedule(cfg.block_order)
    context.task_config["ntrials"] = len(schedule)
    context.task_config["trial_index"] = context.task_config.get("trial_index", 0)

    # Preload tones
    tone_go = QSound(_ensure_tone(700, cfg.cue_duration_s))
    tone_stop = QSound(_ensure_tone(1000, cfg.cue_duration_s))
    tone_switch = QSound(_ensure_tone(400, cfg.cue_duration_s))

    key_left = KEY_MAP.get(cfg.key_left.lower(), Qt.Key.Key_Q)
    key_right = KEY_MAP.get(cfg.key_right.lower(), Qt.Key.Key_P)

    def key_handler(e) -> None:
        nonlocal response_value, response_time_perf
        if response_value is not None:
            return
        try:
            k = e.key()
        except Exception:
            return
        if k == key_left:
            response_value = 1
            response_time_perf = time.perf_counter()
        elif k == key_right:
            response_value = 2
            response_time_perf = time.perf_counter()
        if response_value is not None:
            context.process()

    import time
    context.widget.key_release_handler = key_handler

    for tr_idx in range(int(context.task_config["trial_index"]), len(schedule)):
        tr = schedule[tr_idx]
        # choose delay from current ladder
        if "stop" in tr["trial_type"]:
            tr["delay_s"] = ssd[tr["context"]]
        elif "switch" in tr["trial_type"]:
            tr["delay_s"] = swsd[tr["context"]]

        # jittered timings
        fix_s = random.uniform(cfg.fixation_min_s, cfg.fixation_max_s)
        move_s = random.uniform(cfg.move_min_s, cfg.move_max_s)

        # Fixation
        await context.servicer.publish_state(task_controller_pb2.BehavState(state="fixation"))
        context.widget.renderer = _make_text_renderer(context.widget, "+", cfg.text_size, QColor(255, 255, 255))
        context.widget.update()
        await context.sleep(datetime.timedelta(seconds=fix_s))

        # Movement cue (arrow)
        arrow_txt = "←" if tr["arrow_dir"] == "left" else "→"
        await context.servicer.publish_state(task_controller_pb2.BehavState(state="movement_cue"))
        context.widget.renderer = _make_text_renderer(context.widget, arrow_txt, cfg.text_size, QColor(255, 255, 255))
        context.widget.update()
        await context.sleep(datetime.timedelta(seconds=move_s))

        # GO cue
        await context.servicer.publish_state(task_controller_pb2.BehavState(state="go"))
        context.widget.renderer = _make_circle_renderer(context.widget, cfg.go_circle_radius_px, QColor(255, 255, 255))
        context.widget.update()
        go_on = time.perf_counter()
        if tr["context"] == "auditory":
            tone_go.play()

        # Schedule STOP/SWITCH cue
        cue_on_perf = None
        stop_task = None
        stop_type = tr["trial_type"]

        async def deliver_control_cue():
            nonlocal cue_on_perf
            await context.sleep(datetime.timedelta(seconds=float(tr["delay_s"])))
            if stop_type in ("stop", "stop_ignore"):
                context.widget.renderer = _make_circle_renderer(
                    context.widget, cfg.go_circle_radius_px, QColor(0, 122, 255)
                )
                if tr["context"] == "auditory":
                    tone_stop.play()
            elif stop_type in ("switch", "switch_ignore"):
                context.widget.renderer = _make_circle_renderer(
                    context.widget, cfg.go_circle_radius_px, QColor(255, 140, 0)
                )
                if tr["context"] == "auditory":
                    tone_switch.play()
            context.widget.update()
            cue_on_perf = time.perf_counter()
            await context.sleep(datetime.timedelta(seconds=cfg.cue_duration_s))

        if stop_type != "go":
            stop_task = asyncio.get_event_loop().create_task(deliver_control_cue())

        # Response window
        response_value = None
        response_time_perf = None
        responded = await wait_for(
            context,
            lambda: response_value is not None,
            datetime.timedelta(seconds=cfg.resp_window_s),
        )
        if stop_task:
            try:
                await asyncio.wait_for(stop_task, timeout=0.0)
            except Exception:
                pass

        rt_s = None
        if responded and response_time_perf is not None:
            rt_s = response_time_perf - go_on

        # Outcome logic
        success = None
        if tr["trial_type"] == "go":
            success = response_value is not None and (
                (tr["arrow_dir"] == "left" and response_value == 1)
                or (tr["arrow_dir"] == "right" and response_value == 2)
            )
        elif tr["trial_type"] == "stop":
            success = response_value is None
        elif tr["trial_type"] == "switch":
            success = _eval_switch_success(tr["arrow_dir"], response_value)
        elif tr["trial_type"] in ("stop_ignore", "switch_ignore"):
            success = response_value is not None and (
                (tr["arrow_dir"] == "left" and response_value == 1)
                or (tr["arrow_dir"] == "right" and response_value == 2)
            )

        # Update ladders if active trial
        if not tr["is_control"]:
            ladder = ssd if "stop" in tr["trial_type"] else swsd
            current = ladder[tr["context"]]
            step_dir = 1 if success else -1
            new_val = _clamp(current + cfg.step_s * step_dir, cfg.delay_min_s, cfg.delay_max_s)
            ladder[tr["context"]] = new_val

        # ITI blank
        context.widget.renderer = lambda p: None
        context.widget.update()
        await context.sleep(datetime.timedelta(seconds=cfg.iti_s))

        # Log trial
        trial_result = {
            "trial_index": tr_idx,
            "block": tr["block"],
            "context": tr["context"],
            "trial_type": tr["trial_type"],
            "arrow_dir": tr["arrow_dir"],
            "delay_used": float(tr["delay_s"]),
            "ssd_vis": float(ssd["visual"]),
            "ssd_aud": float(ssd["auditory"]),
            "swsd_vis": float(swsd["visual"]),
            "swsd_aud": float(swsd["auditory"]),
            "resp": int(response_value) if response_value is not None else None,
            "rt": float(rt_s) if rt_s is not None else None,
            "success": success,
            "cue_on_perf": float(cue_on_perf) if cue_on_perf is not None else None,
            "go_on_perf": float(go_on),
        }
        context.behav_result = trial_result
        await context.log(json.dumps({"stopgoswitch_v2_trial": trial_result}))
        context.task_config["trial_index"] = tr_idx + 1

    return TaskResult(True)
