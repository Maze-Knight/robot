from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime import AlreadyRunningError, InstanceLock


class InstanceLockTests(unittest.TestCase):
    def test_second_instance_is_rejected_until_first_releases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bot.lock"
            first = InstanceLock(path)
            second = InstanceLock(path)
            first.acquire()
            try:
                with self.assertRaises(AlreadyRunningError):
                    second.acquire()
            finally:
                first.release()

            second.acquire()
            second.release()


if __name__ == "__main__":
    unittest.main()
