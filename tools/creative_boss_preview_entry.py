"""Launch one automatic backend-editor render milestone, then exit cleanly."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import creative_boss_preview_capture
creative_boss_preview_capture.start(close_editor=True)
