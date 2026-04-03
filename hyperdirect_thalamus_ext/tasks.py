import typing

from thalamus.task_controller.task_context import TaskDescription

from . import stopgo_task


def tasks() -> typing.List[TaskDescription]:
    return [
        TaskDescription(
            "stopgo",
            "STOPGO (Stop-signal)",
            stopgo_task.create_widget,
            stopgo_task.run,
        )
    ]

