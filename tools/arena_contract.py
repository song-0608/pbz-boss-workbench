"""导航调用仅在当前研究进程声明逐项匹配时开放。"""
EXPECTED={
 '/Script/NavigationSystem.NavigationSystemV1.GetNavigationSystem':(16,[
    ('WorldContextObject','ObjectProperty','0x0',8),('ReturnValue','ObjectProperty','0x8',8)]),
 '/Script/NavigationSystem.NavigationSystemV1.K2_ProjectPointToNavigation':(97,[
    ('WorldContextObject','ObjectProperty','0x0',8),('Point','StructProperty','0x8',24),
    ('ProjectedLocation','StructProperty','0x20',24),('NavData','ObjectProperty','0x38',8),
    ('FilterClass','ClassProperty','0x40',8),('QueryExtent','StructProperty','0x48',24),('ReturnValue','BoolProperty','0x60',1)])}
def validate(contract,pids):
    if contract.get('pid')not in pids or contract.get('missing'):raise RuntimeError('Fresh complete navigation declaration required')
    for path,(size,params)in EXPECTED.items():
        rows=[r for r in contract['functions']if r['path']==path]
        if len(rows)!=1 or rows[0]['parameter_bytes']!=size or [(p['name'],p['type'],p['offset'],p['element_size'])for p in rows[0]['parameters']]!=params or any(p.get('array_dim')!=1 for p in rows[0]['parameters']):
            raise RuntimeError('Navigation parameter mismatch: '+path)
        if path.endswith('.K2_ProjectPointToNavigation'):
            projected=rows[0]['parameters'][2]
            if int(projected.get('property_flags','0'),16)&0x100==0:
                raise RuntimeError('Navigation projected location must be a verified output parameter')
    return {'binding_verified':True}
