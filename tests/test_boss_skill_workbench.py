import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_skill_expansion as expansion
import build_boss_skill_workbench as builder
from build_boss_profile_candidate import lua


class SkillWorkbenchTests(unittest.TestCase):
    def fixture(self):
        _,projection=expansion.definition('057_wanjun');actions=projection['actions']
        accepted={a['test_id']:dict(class_path=a['class_path'],activation_runtime_verified=True,
            natural_completion_verified=True,cancellation_runtime_verified=True,gameplay_verified=True,
            movement_runtime_verified=False) for a in actions}
        return actions,accepted

    def test_all_extra_skills_keep_class_and_use_exact_player_slots(self):
        actions,accepted=self.fixture();skills,bindings=builder.additions(actions,accepted,'test-fixture-only')
        self.assertEqual(set(skills),set(expansion.PLAYER_SLOTS.values()))
        self.assertEqual([b['key'] for b in bindings],['F5','F8','F9','Q'])
        self.assertTrue(all(s['evidence']=='test-fixture-only' for s in skills.values()))

    def test_missing_runtime_gate_cannot_enter_player_candidate(self):
        for gate in ('activation_runtime_verified','natural_completion_verified','cancellation_runtime_verified'):
            actions,accepted=self.fixture();accepted['dash'][gate]=False
            with self.subTest(gate=gate):
                with self.assertRaises(AssertionError):builder.additions(actions,accepted,'test')

    def test_no_damage_or_movement_is_not_accepted(self):
        actions,accepted=self.fixture();accepted['dash']['gameplay_verified']=False
        with self.assertRaises(AssertionError):builder.additions(actions,accepted,'test')

    def test_missing_or_wrong_class_is_not_accepted(self):
        actions,accepted=self.fixture();accepted['dash']['class_path']='/Wrong.Class_C'
        with self.assertRaises(AssertionError):builder.additions(actions,accepted,'test')
        del accepted['dash']
        with self.assertRaises(AssertionError):builder.additions(actions,accepted,'test')

    def test_rendered_lua_preserves_base_and_rejects_conflicts(self):
        actions,accepted=self.fixture();skills,bindings=builder.additions(actions,accepted,'test-fixture-only')
        base=b'return {skills={skill_01={class_path="base"}}}'
        profile=builder.patch_profile(base,skills)
        old_bind=b'return {{slot="slot1",id="skill_01",key="F1"}}'
        bound=builder.patch_bindings(old_bind,bindings)
        self.assertIn(base,profile);self.assertIn(old_bind,bound)
        lua_exe=builder.ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'profile.lua').write_bytes(profile);(folder/'bindings.lua').write_bytes(bound)
            script=folder/'verify.lua';script.write_text(
                'local p=dofile('+lua(str(folder/'profile.lua'))+')\n'
                'assert(p.skills.skill_01.class_path=="base")\n'
                'local n=0;for _ in pairs(p.skills)do n=n+1 end;assert(n==5)\n'
                'local b=dofile('+lua(str(folder/'bindings.lua'))+');assert(#b==5)\n',encoding='utf-8')
            result=subprocess.run([str(lua_exe),str(script)],capture_output=True,text=True,encoding='utf-8',errors='replace')
            self.assertEqual(result.returncode,0,result.stderr)
            (folder/'bindings.lua').write_bytes(builder.patch_bindings(old_bind,[dict(bindings[0],key='F1')]))
            result=subprocess.run([str(lua_exe),str(script)],capture_output=True,text=True,encoding='utf-8',errors='replace')
            self.assertNotEqual(result.returncode,0)

    def test_real_four_boss_catalog_accepts_exact_eight_bindings(self):
        base=builder.ROOT/'releases/ahua-boss-workbench-v3-f7034432a74d819b/PBZBossControl/Scripts'
        catalog=(base/'boss_catalog.lua').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'profiles').mkdir()
            (folder/'profiles/ahua.lua').write_bytes((base/'profiles/ahua.lua').read_bytes())
            for identifier,name in builder.PROFILES.items():
                _,projection=expansion.definition(identifier);actions=projection['actions']
                accepted={a['test_id']:dict(class_path=a['class_path'],activation_runtime_verified=True,
                    natural_completion_verified=True,cancellation_runtime_verified=True,gameplay_verified=True,
                    movement_runtime_verified=False) for a in actions}
                skills,bindings=builder.additions(actions,accepted,'unit-test-fixture-only')
                (folder/'profiles'/(name+'.lua')).write_bytes(builder.patch_profile((base/'profiles'/(name+'.lua')).read_bytes(),skills))
                (folder/'profiles'/(name+'_bindings.lua')).write_bytes(builder.patch_bindings((base/'profiles'/(name+'_bindings.lua')).read_bytes(),bindings))
                old="id='"+identifier+"',name="
                lines=[line for line in catalog.splitlines() if old in line]
                self.assertEqual(len(lines),1)
                catalog=catalog.replace(lines[0],lines[0].replace('abilities=4,bindings_count=4','abilities=8,bindings_count=8'))
            (folder/'boss_catalog.lua').write_text(catalog,encoding='utf-8')
            script=folder/'verify.lua'
            script.write_text('package.path='+lua(str(folder/'?.lua')+';'+str(base/'?.lua'))+'\n'
                'local c=require("boss_catalog");local total,count=0,0\n'
                'for _,e in ipairs(c.list())do\n'
                ' local p=c.profile(e.id);local n=0;for _ in pairs(p.skills)do n=n+1 end\n'
                ' assert(n==e.abilities);local config=c.configure(e.id,p);local b=0\n'
                ' for _ in pairs(config.skills)do b=b+1 end;assert(b==e.bindings_count)\n'
                ' total=total+n;count=count+b\nend\nassert(total==52 and count==53)\n',encoding='utf-8')
            result=subprocess.run([str(builder.ROOT.parent/'build/lua-harness/Release/lua-lab.exe'),str(script)],
                capture_output=True,text=True,encoding='utf-8',errors='replace')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
