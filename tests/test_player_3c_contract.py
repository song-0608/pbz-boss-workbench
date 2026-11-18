import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from player_3c_contract import CLASSES,validate

class ContractTests(unittest.TestCase):
    def fixture(self):
        def prop(name,kind,size,offset=0):return dict(name=name,type=kind,element_size=size,array_dim=1,offset=hex(offset))
        return dict(pid=123,classes={path:[prop(name,*spec) for name,spec in names.items()]
            for path,names in CLASSES.items()},functions={
            '/Script/Engine.GameplayStatics.GetWorldDeltaSeconds':dict(parameter_bytes=16,
                parameters=[prop('WorldContextObject','ObjectProperty',8),prop('ReturnValue','DoubleProperty',8,8)]),
            '/Script/Engine.ActorComponent.GetOwner':dict(parameter_bytes=8,
                parameters=[prop('ReturnValue','ObjectProperty',8)])})
    def test_exact_native_declarations(self):self.assertTrue(validate(self.fixture()))
    def test_missing_or_wrong_native_type_rejected(self):
        for change in ('missing','type','size','array','function','old_float','offset','parameter_array'):
            r=copy.deepcopy(self.fixture());p=r['classes']['/Script/Engine.CharacterMovementComponent'][0]
            if change=='missing':r['classes'].pop('/Script/Engine.Character')
            elif change=='function':r['functions']['/Script/Engine.GameplayStatics.GetWorldDeltaSeconds']['parameters'].reverse()
            elif change in ('old_float','offset','parameter_array'):
                p=r['functions']['/Script/Engine.GameplayStatics.GetWorldDeltaSeconds']['parameters'][1]
                if change=='old_float':p.update(type='FloatProperty',element_size=4)
                elif change=='offset':p['offset']='0x4'
                else:p['array_dim']=2
            elif change=='type':p['type']='DoubleProperty'
            elif change=='size':p['element_size']=8
            else:p['array_dim']=2
            with self.assertRaises((AssertionError,KeyError)):validate(r)

if __name__=='__main__':unittest.main()
