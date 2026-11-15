"""导航声明的真实布局、当前进程和输出参数缺一不可。"""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import arena_contract as contract

def fixture():
    return {'pid':123,'missing':[],'functions':[
        {'path':path,'parameter_bytes':size,'parameters':[
            {'name':name,'type':kind,'offset':offset,'element_size':width,'array_dim':1,
             'property_flags':'0x100'if name=='ProjectedLocation'else'0x80'}
            for name,kind,offset,width in parameters]}
        for path,(size,parameters)in contract.EXPECTED.items()]}

class NavigationContract(unittest.TestCase):
    def test_exact_current_declaration(self):
        self.assertEqual(contract.validate(fixture(),{123}),{'binding_verified':True})

    def test_old_pid_missing_function_wrong_vector_and_output_flags(self):
        variants=[]
        old=fixture();old['pid']=999;variants.append(old)
        missing=fixture();missing['missing']=['unresolved'];variants.append(missing)
        size=fixture();size['functions'][1]['parameter_bytes']=96;variants.append(size)
        vector=fixture();vector['functions'][1]['parameters'][1]['element_size']=12;variants.append(vector)
        out=fixture();out['functions'][1]['parameters'][2]['property_flags']='0x80';variants.append(out)
        array=fixture();array['functions'][0]['parameters'][0]['array_dim']=2;variants.append(array)
        duplicate=fixture();duplicate['functions'].append(copy.deepcopy(duplicate['functions'][0]));variants.append(duplicate)
        for data in variants:
            with self.subTest(data=data),self.assertRaises(RuntimeError):contract.validate(data,{123})

if __name__=='__main__':unittest.main()
