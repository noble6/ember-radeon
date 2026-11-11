import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember.app import autotune as AT


def card(scores, errors_at=(), crash_at=()):
    """A fake GPU: scores[mv] is the benchmark score at that offset (0 = stock)."""
    state = {"mv": 0, "applied": []}

    def apply(mv):
        state["applied"].append(mv)
        state["mv"] = 0 if mv is None else mv

    def bench():
        mv = state["mv"]
        return {"ok": mv not in crash_at, "score": None if mv in crash_at else scores.get(mv, scores[0]),
                "power_w": 83 + mv / 3, "temp_c": 70, "errors": ["amdgpu: ring gfx timeout"] if mv in errors_at else []}
    return state, apply, bench


class AutoTuneTests(unittest.TestCase):
    def test_stops_when_performance_really_drops(self):
        st, apply, bench = card({0: 20000, -25: 20050, -50: 17000})
        r = AT.find_undervolt(apply, bench)
        self.assertEqual(r["best"], -25)
        self.assertEqual(r["recommended"], -15)                 # a third less than the last passing step
        self.assertIn("performance dropped 15%", r["stopped"])
        self.assertEqual(st["applied"], [-25, -50, None])       # never past the failing step; restored at the end
        self.assertEqual(len([x for x in r["steps"] if x["mv"] == -50]), 2)   # the bad step was measured twice
        self.assertEqual(st["mv"], 0)

    def test_one_slow_run_is_not_a_verdict(self):
        # Seen on a real RX 6600: a pass at -75 mV scored 14% low only because something
        # else was using the CPU. The second measurement is normal, so the search goes on.
        st, apply, _ = card({0: 20000})
        scores = iter([20000, 20050, 20100, 17041, 20579])       # stock, -25, -50, -75 (disturbed), -75 again

        def bench():
            return {"ok": True, "score": next(scores), "power_w": 80, "temp_c": 70, "errors": []}
        r = AT.find_undervolt(apply, bench)
        self.assertEqual((r["best"], r["recommended"]), (-75, -50))
        self.assertIn("lowest", r["stopped"])

    def test_stops_on_kernel_errors_and_crashes(self):
        st, apply, bench = card({0: 1000}, errors_at=(-50,))
        r = AT.find_undervolt(apply, bench)
        self.assertEqual((r["best"], r["recommended"]), (-25, -15))
        self.assertIn("kernel", r["stopped"])
        self.assertEqual(len(r["steps"]), 2)                     # errors are not retried
        st, apply, bench = card({0: 1000}, crash_at=(-25,))
        r = AT.find_undervolt(apply, bench)
        self.assertEqual((r["best"], r["recommended"]), (0, 0))  # nothing passed: recommend nothing
        self.assertEqual(st["applied"][-1], None)

    def test_never_searches_below_the_cap_or_above_zero(self):
        for floor in (-200, -9999, -100):
            st, apply, bench = card({0: 1000})
            r = AT.find_undervolt(apply, bench, floor_mv=floor)   # the driver may allow far more
            self.assertEqual([m for m in st["applied"] if m is not None], [-25, -50, -75])
            self.assertEqual((r["best"], r["recommended"]), (-75, -50))
        st, apply, bench = card({0: 1000})
        AT.find_undervolt(apply, bench, floor_mv=-60)             # a card with a smaller range
        self.assertEqual([m for m in st["applied"] if m is not None], [-25, -50])
        self.assertTrue(all(m is None or m < 0 for m in st["applied"]))

    def test_always_restores_even_on_failure_or_cancel(self):
        st, apply, bench = card({0: 1000}, crash_at=(0,))
        with self.assertRaises(AT.TuneError):
            AT.find_undervolt(apply, bench)                       # benchmark broken at stock: refuse to go on
        self.assertEqual(st["applied"], [None])
        st, apply, bench = card({0: 1000})

        def boom(mv):
            apply(mv)
            if mv == -50:
                raise AT.TuneError("driver refused")
        with self.assertRaises(AT.TuneError):
            AT.find_undervolt(boom, bench)
        self.assertEqual((st["applied"][-1], st["mv"]), (None, 0))
        st, apply, bench = card({0: 1000})
        calls = []
        r = AT.find_undervolt(apply, bench, cancelled=lambda: calls.append(1) or len(calls) > 2)
        self.assertEqual(r["stopped"], "cancelled")
        self.assertEqual(st["applied"][-1], None)

    def test_margin(self):
        self.assertEqual([AT.recommend(m) for m in (-25, -50, -75)], [-15, -35, -50])


if __name__ == "__main__":
    unittest.main()
