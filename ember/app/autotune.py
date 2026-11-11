"""Automatic undervolt: find how far this card's voltage can come down.

The same procedure a careful person follows by hand: measure at stock, lower the
voltage one small step at a time, put the GPU under load after each step, and stop
at the first sign of trouble. Trouble is a crash, a GPU error in the kernel log, or
the quiet one: the benchmark score falling. Radeon cards that are short on voltage
often keep running but get slower, so a lower score ends the search.

A benchmark score also moves when something else loads the machine, so a step that
fails on its score alone is measured a second time before the search gives up on it.

The load is a short, light benchmark. It finds settings that are clearly too low; it
cannot prove a deep undervolt is stable in every game. So the search stops at -75 mV
however much further the card would go, and recommends a third less than the deepest
step that passed. It never raises voltage and always ends with the card back on the
settings it started with.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time

BENCH = "vkmark"
STEP_MV = 25
SCORE_TOLERANCE = 0.04       # a step may not cost more than 4% of the stock score (noise is about 1%)
MARGIN = 2 / 3               # recommend two thirds of the deepest step that passed
FLOOR_MV = -75               # never search below this, whatever the driver allows
SCENES = ["-b", "shading:shading=phong:duration=10", "-b", "effect2d:kernel=blur:duration=10",
          "-b", "texture:duration=8", "-b", "desktop:duration=8"]
_ERR_RE = re.compile(r"reset|timeout|timed out|error|fail|hang|fault", re.I)


class TuneError(RuntimeError):
    pass


def available() -> bool:
    return bool(shutil.which(BENCH))


def kernel_errors(since: float) -> list[str]:
    """GPU trouble the kernel logged since `since` (empty if the log can't be read)."""
    try:
        out = subprocess.run(["journalctl", "-k", "--no-pager", "--since", f"@{int(since)}"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [l for l in out.splitlines() if re.search(r"amdgpu|\bdrm\b", l, re.I) and _ERR_RE.search(l)]


def run_load(gpu, cancelled=lambda: False) -> dict:
    """One benchmark pass with the sensors sampled alongside."""
    t0 = time.time()
    samples: list[dict] = []
    stop = threading.Event()

    def watch():
        while not stop.wait(0.5):
            samples.append(gpu.snapshot())
    th = threading.Thread(target=watch, daemon=True)
    th.start()
    rc, out = -1, ""
    try:
        proc = subprocess.Popen([BENCH, "--size", "1920x1080", "--present-mode", "immediate"] + SCENES,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 150
        while proc.poll() is None:
            if cancelled() or time.time() > deadline:
                proc.terminate()
                break
            time.sleep(0.3)
        out = proc.communicate(timeout=10)[0] or ""
        rc = proc.returncode
    except (OSError, subprocess.SubprocessError) as e:
        out = str(e)
    finally:
        stop.set()
        th.join(2)
    m = re.search(r"vkmark Score:\s*(\d+)", out)
    busy = [s for s in samples if (s.get("busy") or 0) > 50] or samples

    def avg(k):
        v = [s[k] for s in busy if s.get(k) is not None]
        return sum(v) / len(v) if v else None

    def peak(k):
        v = [s[k] for s in samples if s.get(k) is not None]
        return max(v) if v else None
    return {"ok": rc == 0 and bool(m), "score": int(m.group(1)) if m else None,
            "power_w": avg("power_w"), "temp_c": peak("temp_junction"), "volt_mv": avg("vddgfx_mv"),
            "errors": kernel_errors(t0)}


def verdict(res: dict, base_score: int) -> str:
    """'' if this step is fine, else why the search stops here."""
    if not res.get("ok") or not res.get("score"):
        return "the benchmark crashed"
    if res.get("errors"):
        return "the kernel reported GPU errors"
    if res["score"] < base_score * (1 - SCORE_TOLERANCE):
        return f"performance dropped {round(100 * (1 - res['score'] / base_score))}%"
    return ""


def recommend(best_mv: int) -> int:
    """Back off from the deepest passing step: the test is short, games run for hours."""
    return -int(round(abs(best_mv) * MARGIN / 5.0)) * 5


def find_undervolt(apply, bench, floor_mv: int = FLOOR_MV, progress=lambda *_: None,
                   cancelled=lambda: False, step: int = STEP_MV) -> dict:
    """Search for the deepest stable undervolt.

    apply(mv | None)  puts an offset on the card (None = back to how it was)
    bench()           -> run_load()-style dict
    Returns {baseline, steps: [{mv, score, ...}], best, recommended, stopped}.
    Whatever happens, apply(None) is called at the end.
    """
    floor_mv = max(int(floor_mv), FLOOR_MV)
    plan = list(range(-step, floor_mv - 1, -step))
    total = len(plan) + 1
    out = {"baseline": None, "steps": [], "best": 0, "recommended": 0, "stopped": ""}
    try:
        progress(0, total, "Measuring stock performance")
        base = bench()
        out["baseline"] = base
        if cancelled():
            out["stopped"] = "cancelled"
            return out
        if not base.get("ok") or not base.get("score"):
            raise TuneError("the benchmark did not run at stock settings")
        if base.get("errors"):
            raise TuneError("the kernel reports GPU errors at stock settings")
        for i, mv in enumerate(plan, 1):
            if cancelled():
                out["stopped"] = "cancelled"
                break
            progress(i, total, f"Testing {mv} mV")
            apply(mv)
            res = bench()
            res["mv"] = mv
            out["steps"].append(res)
            if cancelled():
                out["stopped"] = "cancelled"
                break
            why = verdict(res, base["score"])
            if why.startswith("performance dropped"):
                # Could be another program taking CPU time. Measure this step once more.
                progress(i, total, f"Testing {mv} mV again")
                again = bench()
                again["mv"] = mv
                out["steps"].append(again)
                if cancelled():
                    out["stopped"] = "cancelled"
                    break
                why = verdict(again, base["score"])
            if why:
                out["stopped"] = f"{why} at {mv} mV"
                break
            out["best"] = mv
        else:
            out["stopped"] = "reached the lowest voltage Ember tests"
        out["recommended"] = recommend(out["best"]) if out["best"] else 0
        return out
    finally:
        try:
            apply(None)
        except Exception:  # noqa: BLE001 - nothing more we can do here; the caller reports it
            pass
