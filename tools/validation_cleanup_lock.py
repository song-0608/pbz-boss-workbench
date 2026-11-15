"""Serialize competing manual/watchdog cleanup in one validation directory."""
from contextlib import contextmanager
import msvcrt
from pathlib import Path
import time


@contextmanager
def cleanup_lock(state_path, timeout=60):
    path=Path(state_path).with_suffix('.cleanup.lock')
    with path.open('a+b') as stream:
        if stream.seek(0,2)==0:
            stream.write(b'0');stream.flush()
        until=time.monotonic()+timeout
        while True:
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                break
            except OSError:
                if time.monotonic()>=until:
                    raise RuntimeError('Another validation cleanup still owns the session lock')
                time.sleep(.1)
        try:
            yield
        finally:
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
