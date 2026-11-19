import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import boss_combat_script_audit as audit


def local(name):
    return dict(Token='EX_LocalVariable', Variable=dict(Property=dict(Name=name)))


def call(name, module, *parameters):
    return dict(Token='EX_CallMath', Function=dict(ObjectName=f"Class'{name}'", ObjectPath='/Script/'+module),
                Parameters=list(parameters))


def fixture():
    expressions = [
        dict(Token='EX_LetObj', Variable=local('player'), Expression=call('GameplayStatics:GetPlayerPawn',
             'Engine', dict(Token='EX_Self'), dict(Token='EX_IntConst', Value=0))),
        dict(Token='EX_LetObj', Variable=local('avatar'), Expression=call('LGAAction:GetAvatarActor', 'LegoAbility')),
        dict(Token='EX_Let', Variable=local('relation'), Expression=call('FactionUtils:GetFactionRelation',
             'SGameCombatSystem', local('avatar'), local('player'))),
        dict(Token='EX_LetBool', Variable=local('hostile'), Expression=call('KismetMathLibrary:EqualEqual_ByteByte',
             'Engine', local('relation'), dict(Token='EX_ByteConst', Value=2))),
        dict(Token='EX_JumpIfNot', CodeOffset=60, BooleanExpression=local('hostile')),
        dict(Token='EX_LocalVirtualFunction', Function='Spawn Particles', Parameters=[local('avatar')]),
        dict(Token='EX_Return', Expression=dict(Token='EX_Nothing')), dict(Token='EX_EndOfScript')]
    return dict(name='Received_ActionBegin', complete=True,
                statements=[dict(offset=i*10, expression=e) for i,e in enumerate(expressions)])


class CombatScriptAuditTests(unittest.TestCase):
    def test_exact_native_relation_gate_is_simulated_without_game_calls(self):
        function=fixture();before=copy.deepcopy(function)
        self.assertEqual([audit.cue_begin(function,n)['native_spawn_calls'] for n in (0,1,2)], [0,0,1])
        self.assertEqual(function,before)

    def test_partial_script_cannot_prove_a_branch(self):
        for mode in ('incomplete','truncated','duplicate','offset'):
            f=fixture()
            if mode=='incomplete':f['complete']=False
            elif mode=='truncated':f['statements'].pop()
            elif mode=='duplicate':f['statements'][1]['offset']=0
            else:f['statements'][0]['offset']=-1
            with self.subTest(mode=mode),self.assertRaises(ValueError):audit.cue_begin(f,2)

    def test_unresolved_branch_target_is_rejected(self):
        f=fixture();f['statements'][4]['expression']['CodeOffset']=61
        with self.assertRaisesRegex(ValueError,'boundary'):audit.cue_begin(f,0)

    def test_unknown_calls_or_nonlocal_writes_cannot_be_interpreted(self):
        f=fixture();f['statements'][5]['expression']['Function']='Other Action'
        with self.assertRaisesRegex(ValueError,'Unsupported'):audit.cue_begin(f,2)
        f=fixture();f['statements'][0]['expression']['Variable']['Token']='EX_InstanceVariable'
        with self.assertRaisesRegex(ValueError,'nonlocal'):audit.cue_begin(f,2)

    def test_relation_argument_order_and_spawn_owner_are_exact(self):
        f=fixture();f['statements'][2]['expression']['Expression']['Parameters'].reverse()
        with self.assertRaisesRegex(ValueError,'argument order'):audit.cue_begin(f,2)
        f=fixture();f['statements'][5]['expression']['Parameters']=[local('player')]
        with self.assertRaisesRegex(ValueError,'spawn owner'):audit.cue_begin(f,2)

    def test_module_and_query_index_cannot_be_substituted(self):
        f=fixture();f['statements'][0]['expression']['Expression']['Parameters'][1]['Value']=1
        with self.assertRaisesRegex(ValueError,'player query'):audit.cue_begin(f,2)
        f=fixture();f['statements'][2]['expression']['Expression']['Function']['ObjectPath']='/Script/Other'
        with self.assertRaisesRegex(ValueError,'Unsupported'):audit.cue_begin(f,2)

    def test_wrong_function_or_non_enum_input_is_rejected(self):
        for value in (-1,3,False,'2'):
            with self.subTest(value=value),self.assertRaises(ValueError):audit.cue_begin(fixture(),value)
        f=fixture();f['name']='PreviewBegin'
        with self.assertRaises(ValueError):audit.cue_begin(f,2)


if __name__=='__main__':unittest.main()
