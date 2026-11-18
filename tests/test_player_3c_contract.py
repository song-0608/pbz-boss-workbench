import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from player_3c_contract import CLASSES,validate

class ContractTests(unittest.TestCase):
    def fixture(self):
        def prop(name,kind,size):return dict(name=name,type=kind,element_size=size,array_dim=1)
        return dict(pid=123,classes={path:[prop(name,*spec) for name,spec in names.items()]
            for path,names in CLASSES.items()},functions={
            '/Script/Engine.GameplayStatics.GetWorldDeltaSeconds':dict(parameter_bytes=16,
                parameters=[prop('WorldContextObject','ObjectProperty',8),prop('ReturnValue','FloatProperty',4)]),
            '/Script/Engine.ActorComponent.GetOwner':dict(parameter_bytes=8,
                parameters=[prop('ReturnValue','ObjectProperty',8)])})
    def test_exact_native_declarations(self):self.assertTrue(validate(self.fixture()))
    def test_missing_or_wrong_native_type_rejected(self):
        for change in ('missing','type','size','array','function'):
            r=copy.deepcopy(self.fixture());p=r['classes']['/Script/Engine.CharacterMovementComponent'][0]
            if change=='missing':r['classes'].pop('/Script/Engine.Character')
            elif change=='function':r['functions']['/Script/Engine.GameplayStatics.GetWorldDeltaSeconds']['parameters'].reverse()
            elif change=='type':p['type']='DoubleProperty'
            elif change=='size':p['element_size']=8
            else:p['array_dim']=2
            with self.assertRaises((AssertionError,KeyError)):validate(r)

if __name__=='__main__':unittest.main()
