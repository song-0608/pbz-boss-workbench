"""Reuse only unchanged skill execution after exact read-only selection preflight patches."""
import hashlib
from mod_installation import ROOT,validate_package
from build_selection_candidate import BASE,patch_arena,patch_workbench
from yanqiansui_skill_reuse import verify as previous_verify


def verify(current,root=ROOT):
    base=root/'runtime/release-candidates'/BASE
    manifest=validate_package(base)
    previous={n.removeprefix('PBZBossControl/Scripts/'):h for n,h in manifest['files'].items()
        if n.startswith('PBZBossControl/Scripts/')and n!='PBZBossControl/Scripts/main.lua'}
    expected=dict(previous)
    for name,patch in (('owned_arena.lua',patch_arena),('boss_workbench.lua',patch_workbench)):
        source=(base/'PBZBossControl/Scripts'/name).read_bytes().decode('utf-8')
        expected[name]=hashlib.sha256(patch(source).encode('utf-8')).hexdigest()
    expected['boss_selection_preflight.lua']=hashlib.sha256((root/'tools/boss_selection_preflight.lua').read_bytes()).hexdigest()
    assert current==expected,'Only the exact selection preflight patches may reuse ordinary skills'
    return previous_verify(previous,root)
