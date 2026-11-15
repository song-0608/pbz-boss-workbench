import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from player_overlay import latest_status,overlay_layout
row={'at':100,'session':'fixture','expires_at':200,'player':'PC /Fixture.PC','text':'目标：阿花\n生命9000'}
def encode(value):return 'prefix PBZ_PLAYER_UI:STATUS='+json.dumps(value,ensure_ascii=False)+'\n'
assert latest_status(encode(row),'fixture',101)['text']==row['text']
assert latest_status(encode(row),'other',101)is None
assert latest_status(encode(row),'fixture',105)is None
assert latest_status(encode(row),'fixture',99)is None
assert latest_status(encode(row),'fixture',200)is None
assert latest_status(encode(row)+'PBZ_PLAYER_UI:STATUS={broken}\n','fixture',101)is None
for value in (None,[],{},1,'x'*4097):
    bad=dict(row,text=value);assert latest_status(encode(bad),'fixture',101)is None
print('Overlay accepts only current bounded well-formed live status')
menu=overlay_layout('Boss 工作台  |  Insert 开关\n角色 1 / 4',2560)
normal=overlay_layout('新娘阿花 | ACTIVE\nInsert Boss 工作台：选择角色与查看适配状态',2560)
assert menu['menu'] and menu['font_size']==18 and menu['wraplength']==1040
assert not normal['menu'] and normal['font_size']==11 and normal['wraplength']==760
assert overlay_layout('Boss 工作台  |  Insert 开关',800)['font_size']==14
assert overlay_layout('Boss 工作台  |  Insert 开关',800)['wraplength']<=800-48
print('Workbench uses a larger bounded centered presentation; compact HUD remains separate')
