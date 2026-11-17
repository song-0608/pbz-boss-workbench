"""Exercise the Windows batch entry, not only its underlying Python GUI."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows CMD integration')
class WorkbenchCommandEntryTests(unittest.TestCase):
    def test_real_cmd_launcher_opens_and_exits_smoke_from_another_directory(self):
        entry = ROOT / '开始Boss工作台.cmd'
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ['cmd.exe', '/d', '/c', str(entry), '--smoke'], cwd=directory,
                stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0,
            (result.stdout + result.stderr).decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
