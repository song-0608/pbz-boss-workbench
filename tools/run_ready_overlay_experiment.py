"""用途：云同步截图已复核后，执行一次已准备好的叠加层对照，并保证结束时回收。"""
import json
import shutil
import sys
from pathlib import Path
import official_validation as v
import research_window_input as ui
import observe_overlay_experiment as experiment


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1:]!=['--cloud-off-reviewed']:
        raise RuntimeError('Review current research Steam properties screenshot before invoking')
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    if state.get('restored') or not state.get('steam_overlay_block_added'):
        raise RuntimeError('No prepared overlay experiment')
    try:
        source=v.ROOT/'runtime/steam-menu-private.png'
        if source.stat().st_mtime<__import__('datetime').datetime.fromisoformat(state['started_at']).timestamp():
            raise RuntimeError('Properties screenshot is stale')
        shutil.copy2(source,work/'cloud-off-overlay-off-reviewed.png')
        v.save(work/'cloud-gate.json',{'at':v.utc8(),'ui_off_verified':True,
            'review_method':'Current official properties screenshot visually reviewed: cloud OFF and overlay OFF',
            'screenshot':'cloud-off-overlay-off-reviewed.png'})
        ui.click('影之刃零',1238,24,1263,902)
        nvidia=state.get('nvidia_overlay_block_requested',False)
        compatibility=state.get('compatibility_setting')
        v.save(work/'experiment.json',{'at':v.utc8(),
            'factor':compatibility+'=y' if compatibility else 'Block research PBZ access to NVIDIA overlay package nvspcap64.dll/nvppex.dll' if nvidia else 'Block research PBZ access to gameoverlayrenderer64.dll',
            'comparison':'Versus 20261112-200945; same overlays absent, cloud OFF, local Saved virtualization, official original game' if compatibility else 'Versus 20261112-200713; Steam overlay still blocked; same cloud OFF, overlay UI OFF and local Saved virtualization' if nvidia else 'Versus 20261112-195754; same cloud OFF, overlay UI OFF and local Saved virtualization',
            'compatibility_isolation_probe_passed':state.get('compatibility_probe_passed',False),
            'game_binary_modified':False,'gameplay_allowed':False,'loader_deployed':False})
        v.launch(offline=bool(state.get('offline_validation')))
        experiment.main()
    finally:
        v.finish()


if __name__=='__main__':main()
