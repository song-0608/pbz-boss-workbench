"""Collect control, menu and visual declarations in one role-bound metadata pass.

This only reads the explicit union of reflected interfaces used by the candidate.
Completeness never grants bindings, accepts manual animation poses or starts a game.
"""
import argparse
from pathlib import Path

import collect_phantom_boss_control_contract as control
import collect_phantom_boss_visual_contract as visual
import collect_phantom_boss_workbench_contract as workbench

FUNCTIONS=control.FUNCTIONS|visual.FUNCTIONS|workbench.FUNCTIONS
PROPERTIES={path:set(names) for path,names in control.PROPERTIES.items()}
for _requested in (visual.PROPERTIES,workbench.PROPERTIES):
    for _path,_names in _requested.items():PROPERTIES.setdefault(_path,set()).update(_names)
ENUMS=control.ENUMS|workbench.ENUMS|visual.ENUMS
SOURCES=tuple(dict.fromkeys((*control.SOURCES,'tools/collect_phantom_boss_contract_bundle.py',
    'tools/collect_phantom_boss_visual_contract.py','tools/collect_phantom_boss_workbench_contract.py')))


def capture(game):
    result=control.capture(game,functions=FUNCTIONS,requested_properties=PROPERTIES,enums=ENUMS)
    result.update(domains=['control','workbench','visual'],widget_created=False,
        manual_pose_no_notifies_accepted=False,blueprint_image_component_verified=False,
        request_sha256=control.sha(control.canonical(dict(functions=sorted(FUNCTIONS),
            properties={key:sorted(value) for key,value in sorted(PROPERTIES.items())},enums=sorted(ENUMS)))))
    return result


def collect(receipt,role):
    return control.collect(receipt,role,capture_fn=capture,report_stem='native-bundle',sources=SOURCES)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path);parser.add_argument('--role',choices=('host','guest'),required=True)
    args=parser.parse_args();collect(args.receipt,args.role)
