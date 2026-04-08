import typing

from thalamus.task_controller.task_context import TaskDescription

from . import stopgo_task
from . import stopgoswitch_task


def tasks() -> typing.List[TaskDescription]:
    return [
        TaskDescription(
            "stopgo",
            "STOPGO (Stop-signal)",
            stopgo_task.create_widget,
            stopgo_task.run,
        ),
        TaskDescription(
            "stopgoswitch_v2",
            "STOP/GO/SWITCH v2 (visual/auditory)",
            stopgoswitch_task.create_widget,
            stopgoswitch_task.run,
        ),
    ]
