"""
Visual-only STOP/GO/SWITCH task with home-base hold/release requirement.

Design:
- Block order: STOP block -> SWITCH block -> CONTROL block.
- STOP block: 65 GO, 35 STOP.
- SWITCH block: 65 GO, 35 SWITCH.
- CONTROL block: 15 STOP-ignore, 15 SWITCH-ignore (intermixed).
- Visual cues: GO=green, STOP=red, SWITCH=orange.
- Home-base key (default "b") must be pressed to arm each trial.
  Subjects are expected to hold home-base through pre-GO, then release to move.
  We log rt_space_release = (home-base release time - GO onset), which can be negative.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import random
import time
import typing

from thalamus.qt import QColor, QFont, QPainter, QRect, Qt, QWidget, QVBoxLayout
from thalamus.task_controller.widgets import Form
from thalamus.task_controller.util import animate, wait_for, TaskResult
from thalamus import task_controller_pb2
from thalamus.config import ObservableCollection


KEY_MAP = {
    "1": Qt.Key.Key_1,
    "2": Qt.Key.Key_2,
    "q": Qt.Key.Key_Q,
    "p": Qt.Key.Key_P,
    "b": Qt.Key.Key_B,
    "space": Qt.Key.Key_Space,
}


class Config(typing.NamedTuple):
    step_s: float
    delay_start_s: float
    delay_min_s: float
    delay_max_s: float
    control_delay_min_s: float
    control_delay_max_s: float
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
    home_base_key: str
    stopblock_go_n: int
    stopblock_stop_n: int
    switchblock_go_n: int
    switchblock_switch_n: int
    control_stop_ignore_n: int
    control_switch_ignore_n: int


class Trial(typing.TypedDict):
    block: str
    trial_type: str  # go, stop, switch, stop_ignore, switch_ignore
    arrow_dir: str   # left/right
    delay_s: float
    is_control: bool


def create_widget(task_config: ObservableCollection) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout()
    w.setLayout(layout)
    form = Form.build(
        task_config,
        ["Name:", "Value:"],
        Form.Constant("Step size", "step_s", 0.050, "s", precision=3),
        Form.Constant("Delay start", "delay_start_s", 0.300, "s", precision=3),
        Form.Constant("Delay min", "delay_min_s", 0.050, "s", precision=3),
        Form.Constant("Delay max", "delay_max_s", 0.500, "s", precision=3),
        Form.Constant("Control delay min", "control_delay_min_s", 0.200, "s", precision=3),
        Form.Constant("Control delay max", "control_delay_max_s", 0.500, "s", precision=3),
        Form.Constant("Resp window", "resp_window_s", 1.500, "s", precision=3),
        Form.Constant("Cue duration", "cue_duration_s", 0.150, "s", precision=3),
        Form.Constant("Fix min", "fixation_min_s", 1.000, "s", precision=3),
        Form.Constant("Fix max", "fixation_max_s", 1.500, "s", precision=3),
        Form.Constant("Move min", "move_min_s", 1.000, "s", precision=3),
        Form.Constant("Move max", "move_max_s", 1.500, "s", precision=3),
        Form.Constant("ITI", "iti_s", 0.300, "s", precision=3),
        Form.Constant("GO circle radius", "go_radius_px", 90, precision=0),
        Form.Constant("Text size", "text_size", 140, precision=0),
        Form.String("Left key", "key_left", "q"),
        Form.String("Right key", "key_right", "p"),
        Form.String("Home-base key", "home_base_key", "b"),
        Form.Constant("STOP block GO", "stopblock_go_n", 65, precision=0),
        Form.Constant("STOP block STOP", "stopblock_stop_n", 35, precision=0),
        Form.Constant("SWITCH block GO", "switchblock_go_n", 65, precision=0),
        Form.Constant("SWITCH block SWITCH", "switchblock_switch_n", 35, precision=0),
        Form.Constant("Control STOP-ignore", "control_stop_ignore_n", 15, precision=0),
        Form.Constant("Control SWITCH-ignore", "control_switch_ignore_n", 15, precision=0),
    )
    layout.addWidget(form)
    return w


def _read_cfg(task_config: ObservableCollection) -> Config:
    return Config(
        step_s=float(task_config.get("step_s", 0.050)),
        delay_start_s=float(task_config.get("delay_start_s", 0.300)),
        delay_min_s=float(task_config.get("delay_min_s", 0.050)),
        delay_max_s=float(task_config.get("delay_max_s", 0.500)),
        control_delay_min_s=float(task_config.get("control_delay_min_s", 0.200)),
        control_delay_max_s=float(task_config.get("control_delay_max_s", 0.500)),
        resp_window_s=float(task_config.get("resp_window_s", 1.500)),
        cue_duration_s=float(task_config.get("cue_duration_s", 0.150)),
        fixation_min_s=float(task_config.get("fixation_min_s", 1.000)),
        fixation_max_s=float(task_config.get("fixation_max_s", 1.500)),
        move_min_s=float(task_config.get("move_min_s", 1.000)),
        move_max_s=float(task_config.get("move_max_s", 1.500)),
        iti_s=float(task_config.get("iti_s", 0.300)),
        go_circle_radius_px=int(task_config.get("go_radius_px", 90)),
        text_size=int(task_config.get("text_size", 140)),
        key_left=str(task_config.get("key_left", "q")),
        key_right=str(task_config.get("key_right", "p")),
        home_base_key=str(task_config.get("home_base_key", "b")),
        stopblock_go_n=int(task_config.get("stopblock_go_n", 65)),
        stopblock_stop_n=int(task_config.get("stopblock_stop_n", 35)),
        switchblock_go_n=int(task_config.get("switchblock_go_n", 65)),
        switchblock_switch_n=int(task_config.get("switchblock_switch_n", 35)),
        control_stop_ignore_n=int(task_config.get("control_stop_ignore_n", 15)),
        control_switch_ignore_n=int(task_config.get("control_switch_ignore_n", 15)),
    )


def _build_schedule(cfg: Config) -> typing.List[Trial]:
    schedule: typing.List[Trial] = []

    stop_block = ["go"] * max(0, cfg.stopblock_go_n) + ["stop"] * max(0, cfg.stopblock_stop_n)
    switch_block = ["go"] * max(0, cfg.switchblock_go_n) + ["switch"] * max(0, cfg.switchblock_switch_n)
    control_block = ["stop_ignore"] * max(0, cfg.control_stop_ignore_n) + ["switch_ignore"] * max(0, cfg.control_switch_ignore_n)

    random.shuffle(stop_block)
    random.shuffle(switch_block)
    random.shuffle(control_block)

    for t in stop_block:
        schedule.append(
            Trial(
                block="visual_stopblock",
                trial_type=t,
                arrow_dir=random.choice(["left", "right"]),
                delay_s=0.0,
                is_control=False,
            )
        )

    for t in switch_block:
        schedule.append(
            Trial(
                block="visual_switchblock",
                trial_type=t,
                arrow_dir=random.choice(["left", "right"]),
                delay_s=0.0,
                is_control=False,
            )
        )

    for t in control_block:
        schedule.append(
            Trial(
                block="visual_control",
                trial_type=t,
                arrow_dir=random.choice(["left", "right"]),
                delay_s=0.0,
                is_control=True,
            )
        )

    return schedule


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


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


def _make_arrow_renderer(widget: QWidget, dir_str: str, size: int, color: QColor) -> typing.Callable[[QPainter], None]:
    def render(p: QPainter) -> None:
        p.setPen(color)
        p.setFont(QFont("Arial", int(size)))
        w, h = widget.width(), widget.height()
        if dir_str == "left":
            rect = QRect(int(w * 0.05), 0, int(w * 0.4), h)
            txt = "←"
        else:
            rect = QRect(int(w * 0.55), 0, int(w * 0.4), h)
            txt = "→"
        p.drawText(rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter), txt)

    return render


def _with_counter(base_renderer, widget: QWidget, trial_idx: int, total: int) -> typing.Callable[[QPainter], None]:
    def render(p: QPainter) -> None:
        base_renderer(p)
        p.setPen(QColor(200, 200, 200))
        p.setFont(QFont("Arial", 16))
        rect = QRect(0, 0, widget.width() - 10, 30)
        p.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop), f"{trial_idx + 1}/{total}")

    return render


def _set_key_release_handler(widget: QWidget, handler: typing.Optional[typing.Callable]) -> None:
    try:
        widget.key_release_handler = handler
    except Exception:
        pass


def _eval_switch_success(arrow_dir: str, resp: typing.Optional[int]) -> bool:
    if resp is None:
        return False
    if arrow_dir == "left":
        return resp == 2
    return resp == 1


async def _show_block_instruction(context, cfg: Config, block: str) -> None:
    if "stopblock" in block:
        line = "STOP block: cancel response if STOP cue appears."
    elif "switchblock" in block:
        line = "SWITCH block: press the opposite button if SWITCH cue appears."
    else:
        line = "CONTROL block: ignore cues and respond to GO target as normal."

    cue_line = "Visual cues: GO = green, STOP = red, SWITCH = orange."
    home_line = f"Home base key: {cfg.home_base_key.upper()} (release timing is logged relative to GO)."

    text = f"{block}\n{line}\n{cue_line}\n{home_line}\nPress any key to continue."
    renderer = _make_text_renderer(context.widget, text, cfg.text_size, QColor(255, 255, 255))
    context.widget.renderer = renderer
    context.widget.update()

    pressed = False

    def key_handler(_):
        nonlocal pressed
        pressed = True
        context.process()

    old_release = getattr(context.widget, "key_release_handler", None)
    _set_key_release_handler(context.widget, key_handler)
    while not pressed:
        await context.sleep(datetime.timedelta(milliseconds=50))
    _set_key_release_handler(context.widget, old_release)


@animate(60)
async def run(context) -> TaskResult:
    assert context.widget is not None, "Requires canvas (non-remote)"
    cfg = _read_cfg(context.task_config)

    # Independent ladders for STOP and SWITCH in active blocks.
    ssd = float(cfg.delay_start_s)
    swsd = float(cfg.delay_start_s)

    schedule = _build_schedule(cfg)
    context.task_config["ntrials"] = len(schedule)
    context.task_config["trial_index"] = context.task_config.get("trial_index", 0)

    key_left = KEY_MAP.get(cfg.key_left.lower(), Qt.Key.Key_Q)
    key_right = KEY_MAP.get(cfg.key_right.lower(), Qt.Key.Key_P)
    home_key = KEY_MAP.get(cfg.home_base_key.lower(), Qt.Key.Key_B)

    prev_block = None
    total_trials = len(schedule)

    for tr_idx in range(int(context.task_config["trial_index"]), total_trials):
        tr = schedule[tr_idx]
        if tr["block"] != prev_block:
            await _show_block_instruction(context, cfg, tr["block"])
            prev_block = tr["block"]

        # Delay assignment: ladders for active STOP/SWITCH, random for control cues.
        if tr["trial_type"] == "stop":
            tr["delay_s"] = ssd
        elif tr["trial_type"] == "switch":
            tr["delay_s"] = swsd
        elif tr["trial_type"] in ("stop_ignore", "switch_ignore"):
            tr["delay_s"] = random.uniform(cfg.control_delay_min_s, cfg.control_delay_max_s)
        else:
            tr["delay_s"] = 0.0

        fix_s = random.uniform(cfg.fixation_min_s, cfg.fixation_max_s)
        move_s = random.uniform(cfg.move_min_s, cfg.move_max_s)

        response_value: typing.Optional[int] = None
        response_time_perf: typing.Optional[float] = None
        space_release_perf: typing.Optional[float] = None
        cue_on_perf: typing.Optional[float] = None
        go_on: typing.Optional[float] = None

        response_enabled = False
        abort_requested = False
        def key_release_handler(e):
            nonlocal response_value, response_time_perf, space_release_perf, abort_requested
            try:
                k = e.key()
                mods = e.modifiers()
            except Exception:
                return

            if (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)) and k == Qt.Key.Key_E:
                abort_requested = True
                context.process()
                return

            if k == home_key:
                if not response_enabled:
                    return
                if space_release_perf is None:
                    space_release_perf = time.perf_counter()
                    context.process()
                return

            if not response_enabled or response_value is not None:
                return
            if k == key_left:
                response_value = 1
                response_time_perf = time.perf_counter()
                context.process()
            elif k == key_right:
                response_value = 2
                response_time_perf = time.perf_counter()
                context.process()

        _set_key_release_handler(context.widget, key_release_handler)

        # Fixation starts immediately at each trial without home-base gating.
        await context.servicer.publish_state(task_controller_pb2.BehavState(state="fixation"))
        fix_renderer = _with_counter(
            _make_text_renderer(context.widget, "+", cfg.text_size, QColor(255, 255, 255)),
            context.widget,
            tr_idx,
            len(schedule),
        )
        context.widget.renderer = fix_renderer
        context.widget.update()
        fixation_on_perf = time.perf_counter()
        await context.sleep(datetime.timedelta(seconds=fix_s))

        # Movement cue.
        arrow_renderer = _with_counter(
            _make_arrow_renderer(context.widget, tr["arrow_dir"], cfg.text_size, QColor(255, 255, 255)),
            context.widget,
            tr_idx,
            len(schedule),
        )
        await context.servicer.publish_state(task_controller_pb2.BehavState(state="movement_cue"))
        context.widget.renderer = arrow_renderer
        context.widget.update()
        movement_cue_on_perf = time.perf_counter()
        await context.sleep(datetime.timedelta(seconds=move_s))

        # GO cue (visual only, green).
        await context.servicer.publish_state(task_controller_pb2.BehavState(state="go"))

        def composite_go(p):
            arrow_renderer(p)
            _make_circle_renderer(context.widget, cfg.go_circle_radius_px, QColor(0, 200, 0))(p)

        go_renderer = _with_counter(composite_go, context.widget, tr_idx, len(schedule))
        context.widget.renderer = go_renderer
        context.widget.update()
        go_on = time.perf_counter()
        response_enabled = True

        cue_task: typing.Optional[asyncio.Task] = None
        trial_type = tr["trial_type"]

        async def deliver_control_cue() -> None:
            nonlocal cue_on_perf
            await context.sleep(datetime.timedelta(seconds=float(tr["delay_s"])))
            if trial_type in ("stop", "stop_ignore"):
                # STOP cue: red circle.
                def composite_stop(p):
                    arrow_renderer(p)
                    _make_circle_renderer(context.widget, cfg.go_circle_radius_px, QColor(255, 0, 0))(p)

                context.widget.renderer = _with_counter(composite_stop, context.widget, tr_idx, len(schedule))
                context.widget.update()
                cue_on_perf = time.perf_counter()
                await context.sleep(datetime.timedelta(seconds=cfg.cue_duration_s))
            elif trial_type in ("switch", "switch_ignore"):
                # SWITCH cue: orange circle.
                def composite_switch(p):
                    arrow_renderer(p)
                    _make_circle_renderer(context.widget, cfg.go_circle_radius_px, QColor(255, 140, 0))(p)

                context.widget.renderer = _with_counter(composite_switch, context.widget, tr_idx, len(schedule))
                context.widget.update()
                cue_on_perf = time.perf_counter()
                await context.sleep(datetime.timedelta(seconds=cfg.cue_duration_s))

        if trial_type != "go":
            cue_task = asyncio.get_event_loop().create_task(deliver_control_cue())

        if trial_type in ("switch", "switch_ignore"):
            timeout_s = float(tr["delay_s"] + cfg.resp_window_s)
        else:
            timeout_s = cfg.resp_window_s

        responded = await wait_for(
            context,
            lambda: response_value is not None or abort_requested,
            datetime.timedelta(seconds=timeout_s),
        )
        response_enabled = False

        if cue_task is not None:
            if response_time_perf is not None and cue_on_perf is None:
                cue_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cue_task
            else:
                try:
                    await asyncio.wait_for(cue_task, timeout=0.0)
                except Exception:
                    pass

        rt_s = None
        if responded and response_time_perf is not None and go_on is not None:
            rt_s = response_time_perf - go_on

        rt_space_release = None
        if space_release_perf is not None and go_on is not None:
            rt_space_release = float(space_release_perf - go_on)

        success: typing.Optional[bool] = None
        if trial_type == "go":
            success = response_value is not None and (
                (tr["arrow_dir"] == "left" and response_value == 1)
                or (tr["arrow_dir"] == "right" and response_value == 2)
            )
        elif trial_type == "stop":
            success = response_value is None
        elif trial_type == "switch":
            success = _eval_switch_success(tr["arrow_dir"], response_value)
        elif trial_type in ("stop_ignore", "switch_ignore"):
            success = response_value is not None and (
                (tr["arrow_dir"] == "left" and response_value == 1)
                or (tr["arrow_dir"] == "right" and response_value == 2)
            )

        if not tr["is_control"] and trial_type in ("stop", "switch"):
            if trial_type == "stop":
                current = ssd
            else:
                current = swsd

            reached_before_cue = (
                response_time_perf is not None
                and (cue_on_perf is None or response_time_perf < cue_on_perf)
            )
            step_dir = -1 if reached_before_cue else (1 if success else -1)
            new_val = _clamp(current + cfg.step_s * step_dir, cfg.delay_min_s, cfg.delay_max_s)

            if trial_type == "stop":
                ssd = new_val
            else:
                swsd = new_val

        if trial_type in ("stop", "switch") and response_value is not None:
            await context.sleep(datetime.timedelta(milliseconds=200))

        context.widget.renderer = lambda p: None
        context.widget.update()
        await context.sleep(datetime.timedelta(seconds=cfg.iti_s))

        trial_result = {
            "trial_index": tr_idx,
            "block": tr["block"],
            "context": "visual",
            "trial_type": tr["trial_type"],
            "arrow_dir": tr["arrow_dir"],
            "delay_used": float(tr["delay_s"]),
            "ssd_stop_vis": float(ssd),
            "ssd_switch_vis": float(swsd),
            "resp": int(response_value) if response_value is not None else None,
            "rt": float(rt_s) if rt_s is not None else None,
            "rt_space_release": rt_space_release,
            "success": success,
            "cue_on_perf": float(cue_on_perf) if cue_on_perf is not None else None,
            "fixation_on_perf": float(fixation_on_perf),
            "movement_cue_on_perf": float(movement_cue_on_perf),
            "go_on_perf": float(go_on) if go_on is not None else None,
            "fixation_duration_s": float(fix_s),
            "movement_cue_duration_s": float(move_s),
            "movement_to_go_latency_s": float(go_on - movement_cue_on_perf) if go_on is not None else None,
            "home_base_key": cfg.home_base_key,
            "home_base_armed": None,
            "home_base_released": bool(space_release_perf is not None),
            "skipped": False,
        }
        context.behav_result = trial_result
        await context.log(json.dumps({"stopgoswitch_visual_trial": trial_result}))
        context.task_config["trial_index"] = tr_idx + 1

        if abort_requested:
            _set_key_release_handler(context.widget, None)
            return TaskResult(False)

    _set_key_release_handler(context.widget, None)
    return TaskResult(True)
