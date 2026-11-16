"""Draw fixed four-Boss menu textures locally; never opens or calls the game."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
FONT=Path('C:/Windows/Fonts/msyh.ttc')
TARGET=ROOT/'assets/online-workbench'
BOSSES=('新娘阿花','巨锤客：万钧','琴女烟千岁','发狂的水行帮主：游龙')


def build():
    TARGET.mkdir(parents=True,exist_ok=True)
    fonts={size:ImageFont.truetype(str(FONT),size) for size in (22,24,28,38)}
    files={}
    for cursor in range(1,5):
        for selected in range(1,5):
            image=Image.new('RGBA',(1000,620),(16,24,30,246));draw=ImageDraw.Draw(image)
            draw.rounded_rectangle((2,2,997,617),radius=18,outline='#92B2AA',width=2)
            draw.text((42,28),'BOSS 工作台',font=fonts[38],fill='#F2EDDB')
            draw.text((748,42),'联机研究版',font=fonts[24],fill='#A9C4B8')
            draw.line((42,94,958,94),fill='#405852',width=2)
            for index,name in enumerate(BOSSES,1):
                y=118+(index-1)*86
                if index==cursor:
                    draw.rounded_rectangle((36,y,964,y+72),radius=10,fill='#28493F',outline='#AACAAE',width=2)
                draw.text((58,y+17),('›  ' if index==cursor else '   ')+name,font=fonts[28],fill='#E4ECE5')
                if index==selected:draw.text((838,y+22),'使用中',font=fonts[22],fill='#CBE6B1')
            draw.line((42,478,958,478),fill='#405852',width=2)
            draw.text((44,498),'↑ / ↓ 选择    Enter 装配    Insert / Esc 返回',font=fonts[24],fill='#E5E5D4')
            draw.text((44,542),'F6 接管  ·  F10 恢复主角  ·  接管前需完成双方身份确认',font=fonts[22],fill='#A9C4B8')
            name=f'menu-{cursor}-{selected}.png';path=TARGET/name
            image.save(path,format='PNG',optimize=False,compress_level=9)
            files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=dict(schema=1,width=1000,height=620,boss_order=[
        'ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong'],files=files,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        font_sha256=hashlib.sha256(FONT.read_bytes()).hexdigest(),game_started=False)
    (TARGET/'art.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(textures=len(files),output=str(TARGET),game_started=False),ensure_ascii=False))


if __name__=='__main__':build()
