'''Unit tests for IXN_funcs.time_interval (needs napari/qtpy importable).'''
import unittest
from datetime import datetime, timedelta
from pathlib import Path

try:
    from IXN_assembler.IXN_funcs import time_interval
except ImportError as err:     # napari not installed
    time_interval = None
    IMPORT_ERROR = err


@unittest.skipIf(time_interval is None, 'IXN_funcs not importable')
class TestTimeInterval(unittest.TestCase):

    def frames(self, timepoints):
        return [(t, Path(f't{t}.tif')) for t in timepoints]

    def interval(self, timepoints, minutes_per_timepoint=4.0, **kw):
        start = datetime(2026, 10, 2, 16, 13)
        get_time = lambda p: start + timedelta(
            minutes=minutes_per_timepoint * int(p.stem[1:]))
        return time_interval(self.frames(timepoints), get_time=get_time, **kw)

    def test_regular_interval(self):
        self.assertAlmostEqual(self.interval(range(1, 10)), 4.0)

    def test_missing_timepoint_is_not_a_doubled_interval(self):
        self.assertAlmostEqual(self.interval([1, 2, 4, 5, 6]), 4.0)

    def test_single_frame(self):
        self.assertIsNone(self.interval([1]))

    def test_only_first_frames_are_read(self):
        read = []
        def get_time(p):
            read.append(p)
            return datetime(2026, 1, 1) + timedelta(minutes=len(read))
        time_interval(self.frames(range(1, 100)), max_pairs=5, get_time=get_time)
        self.assertEqual(len(read), 6)


if __name__ == '__main__':
    unittest.main()
