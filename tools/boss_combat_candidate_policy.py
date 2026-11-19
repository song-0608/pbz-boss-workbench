"""Shared exclusions for independent developer moves; never an activation grant."""
import re
from boss_offline_inventory import special_ability

ACTOR_CONTEXTS = ('_forseq', '_ending', '_tutorial', '_teaching', '_summon', '_phantom',
                  '_stuntdouble', '_preview', '_stand', '_npchelper', '_npc', '_base')


def deferred_reason(path):
    short = path.rsplit('.', 1)[-1].casefold()
    if special_ability(path):
        return 'utility, phase or dependency needs separate review'
    if '_gex' in short or '_ca_' in short:
        return 'counter-context ability needs a separately verified native trigger'
    if any(token in short for token in ('passive', 'subtitle', 'ritualistheal', 'frontrecovery', 'summon')):
        return 'passive, story, heal, recovery or summon needs separate review'
    if short == 'ga_yanqiansui_skill_01_c':
        return 'historical nonlocal displacement; scene dependency unresolved'
    return None


def ability_reason(path):
    reason = deferred_reason(path)
    if reason:
        return reason
    name = path.rsplit('.', 1)[-1].casefold()
    if any(token in name for token in ('_child', '_ged', '_bed', '_behit', '_qte', '_seq')):
        return 'child, victim or sequence context requires a separate trigger'
    family = re.search(r'(?:^|_)(?:lightattack|middleattack|heavyattack|specialattack|dodge|skill)_', name)
    # Exact verified leaf classes also use Attack_01 / Attack_L and
    # Special_01_hard. These are candidate families, never runtime permission.
    # Keep unnumbered utility names outside this path; context exclusions above
    # still take precedence over an attack-looking resource name.
    direct = re.search(r'(?:^|_)(?:attack_(?:\d+|[lrfb])|special_\d+)(?:_|$)', name)
    if not (family or direct):
        return 'not a reviewed independent combat-input family'
    return None
