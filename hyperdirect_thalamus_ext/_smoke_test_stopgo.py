import asyncio
import json

from thalamus.config import ObservableDict
from thalamus.qt import QApplication

from . import stopgo_task


class _Servicer:
    async def publish_state(self, _msg):
        return None


class _Widget:
    def __init__(self):
        self.key_release_handler = lambda e: None
        self.renderer = lambda p: None

    def width(self):
        return 800

    def height(self):
        return 600

    def update(self):
        return None


class _Ctx:
    def __init__(self, task_config):
        self.task_config = task_config
        self.widget = _Widget()
        self.servicer = _Servicer()
        self.behav_result = {}
        self._log = []

    async def sleep(self, _duration):
        await asyncio.sleep(0)

    def until(self, condition):
        async def inner():
            while not condition():
                await asyncio.sleep(0)

        return asyncio.get_event_loop().create_task(inner())

    def any(self, *awaitables):
        async def inner():
            done, _ = await asyncio.wait(
                [asyncio.ensure_future(f) for f in awaitables],
                return_when=asyncio.FIRST_COMPLETED,
            )
            return await next(iter(done))

        return asyncio.get_event_loop().create_task(inner())

    def process(self):
        return None

    async def log(self, text: str):
        self._log.append(text)


async def _main():
    # Needed because STOPGO uses Qt audio (QSound).
    app = QApplication.instance() or QApplication([])

    # Force all STOP trials, and deterministic stopType balance with seed.
    cfg = ObservableDict(
        {
            "ntrials": 6,
            "stopFrac": 1.0,
            "fixMin": 0.0,
            "fixMax": 0.0,
            "respWindow": 0.0,
            "iti": 0.0,
            "ssdStart": 0.300,
            "ssdStep": 0.050,
            "ssdMin": 0.055,
            "ssdMax": 1.000,
            "goTextSize": 120,
            "stopTextSize": 150,
            "fixationChar": "+",
            "stopChar": "X",
            "stopColor": [255, 0, 0],
            "toneDuration": 0.01,
            "schedule_seed": 123,
            "reset_schedule": True,
        }
    )

    ctx = _Ctx(cfg)
    # Run 6 trials.
    for _ in range(6):
        result = await stopgo_task.run(ctx)
        assert result.success
        assert "trial_index" in ctx.behav_result

    # Validate independent ladder updates: end values match #vis/#aud stop trials.
    stop_types = list(cfg["stopType"])
    n_vis = sum(1 for x in stop_types if x == stopgo_task.STOP_VIS)
    n_aud = sum(1 for x in stop_types if x == stopgo_task.STOP_AUD)

    expected_vis = min(1.0, 0.3 + 0.05 * n_vis)
    expected_aud = min(1.0, 0.3 + 0.05 * n_aud)
    assert abs(float(cfg["ssd_vis"]) - expected_vis) < 1e-9
    assert abs(float(cfg["ssd_aud"]) - expected_aud) < 1e-9

    # Validate log contains per-trial JSON payload.
    decoded = [json.loads(x)["stopgo_trial"] for x in ctx._log]
    assert len(decoded) == 6
    for tr in decoded:
        for k in (
            "trial_index",
            "isStop",
            "stopType",
            "goInstr",
            "ssdUsed",
            "ssdVisStart",
            "ssdAudStart",
            "ssdVisEnd",
            "ssdAudEnd",
            "goOn_perf_counter_s",
            "stopOn_perf_counter_s",
            "resp",
            "rt",
            "stopSuccess",
        ):
            assert k in tr


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()

