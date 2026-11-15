"""只读核对导航投影接口，为地形约束的训练角色装配提供声明依据。"""
import json
from pathlib import Path
import struct
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields
FUNCTIONS={
    '/Script/NavigationSystem.NavigationSystemV1.K2_ProjectPointToNavigation',
    '/Script/NavigationSystem.NavigationSystemV1.GetNavigationSystem',
}
def collect():
    rows=[]
    with GameRead()as g:
        for row in g.find_native({p.rsplit('.',1)[1]for p in FUNCTIONS},prefixes=('/Script/NavigationSystem.',)):
            if row['path']not in FUNCTIONS:continue
            address=int(row['address'],16)
            rows.append({'path':row['path'],'parameter_bytes':struct.unpack('<H',g.read(address+0x106,2))[0],
                'parameters':[p for p in fields(g,address,32)if int(p['property_flags'],16)&0x80]})
        result={'at':v.utc8(),'pid':g.pid,'functions':rows,'missing':sorted(FUNCTIONS-{r['path']for r in rows}),
                'scope':'read-only navigation declarations; no pathfinding or gameplay calls'}
        target=Path(g.state['work'])/'arena-native-contract.json';v.save(target,result)
    print(json.dumps({'report':str(target),**result},ensure_ascii=False))
if __name__=='__main__':collect()
