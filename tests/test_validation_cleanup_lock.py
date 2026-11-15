import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class CleanupLockTests(unittest.TestCase):
    def test_watchdog_and_manual_cleanup_share_one_restoration(self):
        # Real separate processes exercise the OS lock; no sandbox/game policy is touched.
        worker='''import json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from validation_cleanup_lock import cleanup_lock
p=Path(sys.argv[2])
with cleanup_lock(p):
 data=json.loads(p.read_text())
 if not data['restored']:
  time.sleep(.25)
  data['restorations']+=1;data['restored']=True
  p.write_text(json.dumps(data))
'''
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)/'state.json'
            state.write_text(json.dumps({'restored':False,'restorations':0}))
            commands=[[sys.executable,'-c',worker,str(ROOT/'tools'),str(state)] for _ in range(2)]
            processes=[subprocess.Popen(c,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for c in commands]
            for process in processes:
                out,error=process.communicate(timeout=10)
                self.assertEqual(process.returncode,0,error.decode())
            self.assertEqual(json.loads(state.read_text()),{'restored':True,'restorations':1})


if __name__=='__main__':unittest.main()
