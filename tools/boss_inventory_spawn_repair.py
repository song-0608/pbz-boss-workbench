"""Resolve current target assets in newly generated inventory experiments only.

The accepted v5 and historical research workflows remain immutable. The target
resolver is embedded because the historical deployer only enumerates modules
already present in the accepted release.
"""
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha
from build_player_experience_candidate import replace
from mod_installation import validate_package


BASE = 'ahua-boss-workbench-v5-3f29975fe3b8826f'
MODULE = 'PBZBossControl/Scripts/owned_arena.lua'
SOURCES = ('tools/boss_inventory_spawn_repair.py', 'tools/player_spawn_assets.lua',
           'tests/test_boss_inventory_spawn_repair.py', 'tests/test_inventory_spawn_assets.lua')
RESOLVER_END = '-- End current target asset resolver.\n'


def payload(root=ROOT):
    base = root / 'releases' / BASE
    manifest = validate_package(base)
    assert manifest['release_id'] == BASE
    source = base / MODULE
    assert sha(source) == manifest['files'][MODULE], 'preserve accepted arena source'
    text = source.read_text(encoding='utf-8').replace('\r\n', '\n')
    text = replace(text, '        local target_class=class\n',
                   '        local target_class=class\n        local target_profile=assembly_profile\n')
    text = replace(text, '            local target_profile=require(assembly_profile.training_target_profile)',
                   '            target_profile=require(assembly_profile.training_target_profile)')
    text = replace(text, '        local function spawn_training_target(index)\n',
                   '        local function spawn_training_target(index)\n'
                   '            guard()\n'
                   '            local target_class,controller_class,maths,statics=inventory_spawn_assets.target(\n'
                   '                _G,target_profile,valid,log)\n')
    helper = (root / 'tools/player_spawn_assets.lua').read_text(encoding='utf-8').replace('\r\n', '\n')
    return ('local inventory_spawn_assets=(function()\n' + helper + '\nend)()\n'
            + RESOLVER_END + text).encode('utf-8')


def overrides(root=ROOT):
    return {'owned_arena.lua': payload(root)}


def source_hashes(root=ROOT):
    return {name: sha(root / name) for name in SOURCES}
