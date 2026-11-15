"""用途：只截取活跃离线研究箱中的游戏画面，附1280宽预览便于准确定位菜单。"""
import json
from pathlib import Path
import re
import sys
import time
from PIL import Image
import official_validation as v
from test_game_with_offline_client import game_capture


def capture(label):
    if not re.fullmatch(r'[a-z0-9-]{1,64}',label):raise ValueError('Bounded evidence label required')
    s=json.loads(v.state_path().read_text(encoding='utf-8'))
    if s.get('restored') or s.get('network_active') or not s.get('offline_validation') or time.time()>=s['deadline_unix']:
        raise RuntimeError('Active strictly offline research session required')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if c.host_steam_pids(dll):raise RuntimeError('Preserve host Steam')
    work=Path(s['work']);target=work/(label+'.png')
    result=game_capture(dll,target)
    if result.get('captured'):
        with Image.open(target) as pic:
            pic.resize((1280,round(pic.height*1280/pic.width))).save(work/(label+'-preview.png'))
        result['preview']=str(work/(label+'-preview.png'))
    return result


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(capture(sys.argv[1]),ensure_ascii=False))
