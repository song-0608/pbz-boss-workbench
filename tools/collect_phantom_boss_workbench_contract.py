"""Read current-role UMG declarations only; never creates a widget or issues a binding."""
import argparse
import json
from pathlib import Path
import struct

from build_phantom_boss_candidate import ROOT, canonical, sha
from inspect_pbz_ai_metadata import fields
from phantom_boss_online_readonly import OnlineGameRead

FUNCTIONS={
    '/Script/Engine.KismetRenderingLibrary.ImportFileAsTexture2D',
    '/Script/UMG.WidgetBlueprintLibrary.Create',
    '/Script/UMG.UserWidget.AddToViewport',
    '/Script/UMG.UserWidget.IsInViewport',
    '/Script/UMG.UserWidget.SetAlignmentInViewport',
    '/Script/UMG.UserWidget.SetDesiredSizeInViewport',
    '/Script/UMG.UserWidget.SetPositionInViewport',
    '/Script/UMG.Widget.SetVisibility',
    '/Script/UMG.Widget.GetVisibility',
    '/Script/UMG.Widget.GetDesiredSize',
    '/Script/UMG.Widget.SetRenderScale',
    '/Script/UMG.Widget.RemoveFromParent',
    '/Script/UMG.Image.SetBrushFromTexture',
    '/Script/UMG.WidgetLayoutLibrary.GetViewportSize',
    '/Script/UMG.WidgetLayoutLibrary.GetViewportScale',
}


def collect(receipt,role):
    receipt=Path(receipt).resolve()
    declarations=[]
    with OnlineGameRead(receipt,role) as game:
        for row in game.find_native({p.rsplit('.',1)[1] for p in FUNCTIONS},
                prefixes=('/Script/Engine.','/Script/UMG.')):
            if row['path'] not in FUNCTIONS:continue
            address=int(row['address'],16)
            declarations.append(dict(path=row['path'],
                parameter_bytes=struct.unpack('<H',game.read(address+0x106,2))[0],
                parameters=[p for p in fields(game,address,32) if int(p['property_flags'],16)&0x80]))
        report=dict(schema=1,status='declarations-only',role=role,pid=game.pid,
            session_sha256=sha(receipt.read_bytes()),functions=declarations,
            missing_functions=sorted(FUNCTIONS-{r['path'] for r in declarations}),
            binding_verified=False,widget_created=False,game_functions_called=False,
            inventory_inspected=False,memory_written=False,runtime_acceptance_current=False,
            source_sha256={name:sha((ROOT/name).read_bytes()) for name in (
                'tools/collect_phantom_boss_workbench_contract.py','tools/phantom_boss_online_readonly.py')})
    target=receipt.parent/(role+'-workbench-declarations.json')
    with target.open('xb')as stream:stream.write(canonical(report)+b'\n')
    print(json.dumps(dict(report=str(target),functions=len(declarations),missing=report['missing_functions'],
        binding_verified=False),ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path);parser.add_argument('--role',choices=('host','guest'),required=True)
    args=parser.parse_args();collect(args.receipt,args.role)
