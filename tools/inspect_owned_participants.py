"""Read only the exact latest assembly participants; resolve health fields from live reflection."""
import json
from pathlib import Path
import re
import struct
import time
import ahua_practice as practice
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields


def collect():
    _,state=practice.owned_session()
    raw_text=practice.log_path(state).read_text(encoding='utf-8',errors='replace')
    text=raw_text[raw_text.rfind('PBZ_CONTROL_LIFECYCLE:SETUP_PLAYER_BASELINE='):]
    paths=re.findall(r'PBZ_CONTROL_LIFECYCLE:(?:SETUP_PLAYER_BASELINE|SPAWNED|TRAINING_TARGET_[12])=[^ ]+ ([^\r\n|]+)',text)
    assert len(paths)==4 and len(set(paths))==4,'one exact current assembly required'
    addresses={path:int(address)for path,address in re.findall(
        r'SPAWN_STATE=(?:after_finish|target_after_finish_[12])\|object=[^ ]+ ([^|\r\n]+)\|address=(\d+)',text)}
    players=re.findall(r'PLAYER_READY_HEALTH=[^ ]+ ([^|\r\n]+)\|(\d+)\|health=',raw_text)
    for path,address in players:
        if path==paths[0]:addresses[path]=int(address)
    assert set(addresses)==set(paths),'four exact declared addresses required; no broad object scan'
    with GameRead()as g:
        def prop(owner,name):
            for _ in range(24):
                for p in fields(g,owner,512):
                    if p['name']==name:return p
                owner=g.u64(owner+0x40)
                if not owner:break
            raise RuntimeError('live property unavailable: '+name)
        rows=[]
        for path in paths:
            a=addresses[path]
            try:
                assert g.path(a).replace('.PersistentLevel.',':PersistentLevel.')==path,'participant identity changed'
                h=g.header(a);attribute=prop(h['class'],'AttributeSetBase')
                attrs=g.u64(a+int(attribute['offset'],16));health=prop(g.header(attrs)['class'],'Health')
                health_type=g.u64(int(health['descriptor'],16)+0x70)
                current=prop(health_type,'CurrentValue');assert current['element_size']==4
                hp=struct.unpack('<f',g.read(attrs+int(health['offset'],16)+int(current['offset'],16),4))[0]
                root_prop=prop(h['class'],'RootComponent');root=g.u64(a+int(root_prop['offset'],16))
                location=prop(g.header(root)['class'],'RelativeLocation')
                velocity=prop(g.header(root)['class'],'ComponentVelocity')
                assert location['element_size']==velocity['element_size']==24
                rows.append({'path':g.path(a),'address':hex(a),'health':hp,
                    'position':struct.unpack('<ddd',g.read(root+int(location['offset'],16),24)),
                    'velocity':struct.unpack('<ddd',g.read(root+int(velocity['offset'],16),24))})
                if len(rows)==4:break
            except (OSError,ValueError,UnicodeError):continue
        assert len(rows)==4,'exact participant read incomplete'
        result={'pid':g.pid,'at':time.time(),'scope':'read-only exact player and owned actors; live reflected health/position/velocity',
            'rows':rows}
    target=Path(state['work'])/('owned-participants-'+str(time.time_ns())+'.json')
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':collect()
