"""Capture role-bound UMG declarations; never create widgets or grant bindings."""
import argparse
from pathlib import Path
import collect_phantom_boss_control_contract as control

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
PROPERTIES={path:set() for path in ('/Script/UMG.Image','/Script/UMG.UserWidget','/Script/UMG.Widget')}
ENUMS={'/Script/UMG.ESlateVisibility'}
SOURCES=(*control.SOURCES,'tools/collect_phantom_boss_workbench_contract.py')


def capture(game):
    result=control.capture(game,functions=FUNCTIONS,requested_properties=PROPERTIES,enums=ENUMS)
    result.update(domains=['workbench'],widget_created=False,blueprint_image_component_verified=False)
    return result


def collect(receipt,role):
    return control.collect(receipt,role,capture_fn=capture,report_stem='workbench',sources=SOURCES)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path);parser.add_argument('--role',choices=('host','guest'),required=True)
    args=parser.parse_args();collect(args.receipt,args.role)
