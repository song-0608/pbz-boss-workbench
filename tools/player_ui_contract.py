"""校验本进程的完整声明后才允许玩家HUD与视线调用。"""
EXPECTED = {
    '/Script/Engine.HUD.DrawText': (53, [
        ('Text','StrProperty','0x0',16),('TextColor','StructProperty','0x10',16),
        ('ScreenX','FloatProperty','0x20',4),('ScreenY','FloatProperty','0x24',4),
        ('Font','ObjectProperty','0x28',8),('Scale','FloatProperty','0x30',4),('bScalePosition','BoolProperty','0x34',1)]),
    '/Script/Engine.HUD.ReceiveDrawHUD': (8, [('SizeX','IntProperty','0x0',4),('SizeY','IntProperty','0x4',4)]),
    '/Script/Engine.HUD.GetOwningPlayerController': (8, [('ReturnValue','ObjectProperty','0x0',8)]),
    '/Script/Engine.Controller.LineOfSightTo': (34, [
        ('Other','ObjectProperty','0x0',8),('ViewPoint','StructProperty','0x8',24),
        ('bAlternateChecks','BoolProperty','0x20',1),('ReturnValue','BoolProperty','0x21',1)]),
    '/Script/Engine.KismetSystemLibrary.PrintString': (56, [
        ('WorldContextObject','ObjectProperty','0x0',8),('InString','StrProperty','0x8',16),
        ('bPrintToScreen','BoolProperty','0x18',1),('bPrintToLog','BoolProperty','0x19',1),
        ('TextColor','StructProperty','0x1c',16),('duration','FloatProperty','0x2c',4),('Key','NameProperty','0x30',8)]),
}


def validate(contract, pids):
    if contract.get('pid') not in pids or contract.get('passed') is not True:
        raise RuntimeError('Fresh successful player UI declaration required')
    for path,(size,parameters) in EXPECTED.items():
        rows=[r for r in contract['functions'] if r['path']==path]
        if len(rows)!=1 or rows[0]['parameter_bytes']!=size:
            raise RuntimeError('Player UI function mismatch: '+path)
        actual=[(p['name'],p['type'],p['offset'],p['element_size']) for p in rows[0]['parameters']]
        if actual!=parameters or any(p['array_dim']!=1 for p in rows[0]['parameters']):
            raise RuntimeError('Player UI parameter mismatch: '+path)
    return {'binding_verified': True}
