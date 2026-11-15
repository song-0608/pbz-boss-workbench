"""拒绝只有Lua回调注册、缺少真实引擎LoadMap detour的装配。"""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from ahua_practice import validate_map_travel_loader


class LoaderTests(unittest.TestCase):
    def test_resolved_opt_in(self):
        validate_map_travel_loader({'load_map_hook_trial':True},
            'GameEngine::LoadMap address 0x143f12340\n[UE4SS.LoadMap.LuaModImpl] Added prehook with Id 1')

    def test_ordinary_player_entry_requires_the_same_real_hook(self):
        validate_map_travel_loader({'load_map_hook_enabled':True,'load_map_hook_trial':False},
            'GameEngine::LoadMap address 0x143f12340\n[UE4SS.LoadMap.LuaModImpl] Added prehook with Id 1')
        with self.assertRaises(RuntimeError):
            validate_map_travel_loader({'load_map_hook_enabled':True}, 'MAP_TRAVEL_GUARD_READY=true')

    def test_registration_only_or_missing_opt_in(self):
        for state,text in (({},'GameEngine::LoadMap address 0x143f12340'),
                           ({'load_map_hook_trial':True},'MAP_TRAVEL_GUARD_READY=true'),
                           ({'load_map_hook_trial':True},'GameEngine::LoadMap address 0x143f12340')):
            with self.subTest(state=state,text=text),self.assertRaises(RuntimeError):
                validate_map_travel_loader(state,text)

    def test_failed_or_disabled_detour(self):
        for error in ('[LoadMap] Tried to install hook but hooking is disabled for this function.',
                      '[UE4SS.LoadMap.LuaModImpl] Failed to add hook, detour installation likely failed!'):
            with self.subTest(error=error),self.assertRaises(RuntimeError):
                validate_map_travel_loader({'load_map_hook_trial':True},'GameEngine::LoadMap address 0x143f12340\n'+error)


if __name__=='__main__':unittest.main()
