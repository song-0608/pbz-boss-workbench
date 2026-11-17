"""Bounded integration input for the exact experience candidate and owned window."""
import argparse
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import time

from player_experience_trial import gate
import ahua_practice as practice
import official_validation as v


def send_fixed_chord(user, window, action, sleep=time.sleep):
    """No arbitrary key API: one short Shift+W+F1 trial or one middle click."""
    assert action in ('shift_cast','lock')
    pressed=[];mouse=False
    def focused():
        assert int(user.GetForegroundWindow()or 0)==window, 'Research window lost focus'
    try:
        focused()
        if action=='lock':
            user.mouse_event(0x20,0,0,0,0);mouse=True;sleep(.12);focused()
        else:
            for key in (0x10,0x57):
                focused();user.keybd_event(key,0,0,0);pressed.append(key)
            sleep(.35);focused()
            user.keybd_event(0x70,0,0,0);pressed.append(0x70)
            sleep(.14);focused()
    finally:
        for key in reversed(pressed):user.keybd_event(key,0,2,0)
        if mouse:user.mouse_event(0x40,0,0,0,0)


def main(flow,action):
    request=gate(flow,action)
    assert time.time()<request['gate_expires_at']
    user=ctypes.WinDLL('user32',use_last_error=True);user.GetForegroundWindow.restype=w.HWND
    assert int(user.GetForegroundWindow()or 0)==request['window_id']
    outcome=dict(request,dispatch_at=v.utc8(),input_sent=False)
    owner,state=practice.owned_session()
    path=Path(state['work'])/('experience-dispatch-'+str(time.time_ns())+'.json')
    try:
        if action in ('shift_cast','lock'):
            send_fixed_chord(user,request['window_id'],action)
        else:
            import research_game_menu as menu
            purpose={'enter':'control_enter','exit':'control_exit','cycle_target':'control_target',
                'cast':'control_registered_skill_slot1','workbench':'control_workbench_toggle',
                'down':'control_workbench_down','up':'control_workbench_up',
                'confirm':'control_workbench_confirm','close':'control_workbench_close'}[action]
            outcome['native_dispatch']=menu.click(0,0,2560,1600,purpose)
        outcome['input_sent']=True
    except Exception as error:
        outcome['error']=type(error).__name__+': '+str(error)
        raise
    finally:
        v.save(path,outcome)
        print('dispatch_record='+str(path),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow',type=Path)
    parser.add_argument('action',choices=('shift_cast','lock','enter','exit','cycle_target','cast',
        'workbench','down','up','confirm','close'))
    args=parser.parse_args();main(args.workflow.resolve(),args.action)
