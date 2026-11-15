"""用途：离线可测试的候选筛选规则；名称线索不等于Boss身份。"""
import re

# 用途：按路径/下划线边界匹配，避免把Dahua、Guahua或十六进制片段当作阿花。
BRIDE_TOKEN = re.compile(r'(?:^|[/_.:\s-])(?:a_?hua|xin_?niang|bride)(?=$|[/_.:\s-])', re.I)
NPC_BASE = re.compile(r'(?:^|\.)(?:PBZCharacter_NPC|PBZCharacter_Boss)$', re.I)
CHARACTER_ASSET = re.compile(r'(?:^|\.)(?:BP_)?(?:Monster|NPC|Boss|Enemy|Character)(?:_|$)', re.I)


def bride_name_match(value):
    return bool(BRIDE_TOKEN.search(value) or '\u963f\u82b1' in value or '\u65b0\u5a18' in value)


def npc_lineage(paths):
    return any(NPC_BASE.search(path) for path in paths)


def useful_character_class(path, lineage):
    return npc_lineage(lineage) or ('/Mobs/' in path and bool(CHARACTER_ASSET.search(path)))
