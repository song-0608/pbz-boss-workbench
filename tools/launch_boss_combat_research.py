"""Launch a declared input-helper experiment through the unchanged player launcher."""
import argparse
from pathlib import Path
import ahua_practice as practice
import pbz_ue4ss_baseline as loader
from boss_native_input_artifact import verify


def launch(smoke):
    verify(smoke)
    original=loader.deploy_and_launch
    def declared(**kwargs):
        assert kwargs==dict(with_signature=True,readonly_ai=True,readonly_hot_reload=True,load_map_hook_trial=True)
        return original(**kwargs,native_input_smoke=smoke)
    loader.deploy_and_launch=declared
    try:practice.launch(True,load_map_hook_trial=True)
    finally:loader.deploy_and_launch=original


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_input_smoke',type=Path)
    parser.add_argument('--cloud-off-reviewed',action='store_true',required=True)
    args=parser.parse_args();launch(args.native_input_smoke)
