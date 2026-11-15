"""用途：区分玩家F10恢复、自动限时收尾和仅按键未激活，防止验收误报。"""
import math
import re


def world_retirement_result(text):
    events=list(re.finditer(r'\[PBZBossControl\] world_retired success=true state=OFF reason=old world and modified participants disposed',text))
    if not events:return {'passed':False,'reason':'no complete old-world retirement'}
    event=events[-1];before=text[:event.start()];tail=text[event.end():]
    entered=before.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    requested=before.rfind('ACTIVE_WORLD_TRIAL_REQUESTED=true')
    disposed=before.rfind('PBZ_CONTROL_WORLD:OLD_OBJECTS_DISPOSED=true')
    boundary=re.search(r'SPAWN_ATTEMPT=|\[PBZBossControl\] enter success=',tail)
    cleanup_tail=tail[:boundary.start()]if boundary else tail
    labels=set(re.findall(r'OWNED_DESTROY_VERIFIED=([^|\r\n]+)\|engine_unusable=true',cleanup_tail))
    expected={'boss','boss_controller','target','target_controller','extra_target','extra_target_controller'}
    passed=(0<=entered<requested<disposed and expected<=labels
            and 'WORLD_REASSEMBLY_WAIT=true'in cleanup_tail and 'state=FAULTED'not in text[entered:]
            and 'PBZ_CONTROL_LIFECYCLE:ISSUE_'not in text[entered:])
    return {'passed':passed,'old_modified_objects_disposed':disposed>requested,
            'owned_cleanup_labels':sorted(labels),'retirement_event_end':event.end(),
            'new_world_ready':False}


def restoration_result(segment, label=None, reason=None):
    """用途：退出提示、主角位置、输入与镜头清理必须属于同一次恢复。"""
    events = list(re.finditer(
        r'\[PBZBossControl\] (exit|menu_exit|auto_exit) success=true state=OFF reason=([^\r\n]*)', segment))
    selected = [event for event in events
                if (label is None or event.group(1) == label)
                and (reason is None or event.group(2) == reason)]
    if not selected:
        return {'passed': False, 'reason': 'matching restoration event missing'}
    event = selected[-1]
    tail = segment[event.end():]
    # 用途：下一次接管及恢复的回读不能补齐这次缺失的证据。
    boundary = re.search(r'\[PBZBossControl\] (?:enter|exit|menu_exit|auto_exit) success=', tail)
    if boundary:
        tail = tail[:boundary.start()]
    delta = re.search(r'ORIGINAL_PLAYER_POSITION_DELTA=([^\r\n]+)', tail)
    active = re.search(r'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=(\d+)', tail)
    try:
        position = float(delta.group(1)) if delta else None
    except ValueError:
        position = None
    result = {'label': event.group(1), 'reason': event.group(2),
              'player_position_delta': position,
              'player_new_active_count': int(active.group(1)) if active else None,
              'camera_cleanup_verified': 'CAMERA_CLEANUP_ENGINE_VERIFIED=true' in tail}
    result['passed'] = bool(position is not None and math.isfinite(position) and abs(position) <= .01
                            and result['player_new_active_count'] == 0
                            and result['camera_cleanup_verified']
                            and 'state=FAULTED' not in segment
                            and 'PBZ_CONTROL_RESTORE:FAILED=' not in segment)
    return result


def cancellation_result(segment, skill):
    # 用途：必须依次出现本招激活、真实活动、取消归零和玩家退出；stop不能替代exit。
    tokens = (r'KEY_SKILL_BEGIN=' + re.escape(skill) + r'\|',
              r'CANCEL_ACTIVE_BEFORE=[1-9]\d*', r'CANCEL_RESULT=true\|active=0',
              r'\[PBZBossControl\] exit success=true state=OFF')
    cursor = 0
    for pattern in tokens:
        match = re.search(pattern, segment[cursor:])
        if not match:
            return False
        cursor += match.end()
    return 'state=FAULTED' not in segment and 'PBZ_CONTROL_RESTORE:FAILED=' not in segment


def death_restoration_result(segment, native=False, active_skill=None):
    # 用途：Kill后原生销毁和生命耗尽分别验收，不能用仍为9000的血量伪造扣血死亡。
    reason = 'owned boss disposed' if native else 'boss health depleted'
    result = restoration_result(segment, 'auto_exit', reason)
    result['death_kind'] = 'native_owned_disposal' if native else 'health_depleted'
    if native:
        begin = segment.find('OWNED_DEATH_TRIAL_BEGIN=')
        request = segment.find('OWNED_DEATH_TRIAL_KILL_REQUESTED=true', begin)
        disposed = segment.find('PBZ_CONTROL_RESTORE:OWNED_DISPOSAL_VERIFIED=true', request)
        exit_at = segment.find('[PBZBossControl] auto_exit success=true state=OFF reason=owned boss disposed', disposed)
        read_at = segment.find('CONTROLLED_BOSS_DISPOSED=true', exit_at)
        result['owned_disposal_verified'] = begin >= 0 and begin < request < disposed < exit_at < read_at
        result['hp_depletion_verified'] = False
        result['passed'] = result['passed'] and result['owned_disposal_verified']
    if active_skill:
        active=re.search(r'OWNED_DEATH_TRIAL_ACTIVE_SKILL='+re.escape(active_skill)+r'\|active=([1-9]\d*)',segment)
        begin=segment.find('OWNED_DEATH_TRIAL_BEGIN=')
        request=segment.find('OWNED_DEATH_TRIAL_KILL_REQUESTED=true')
        result['active_skill_at_request']=active_skill if active and begin<active.start()<request else None
        result['active_count_at_request']=int(active.group(1))if active else None
        result['active_at_object_disposal_verified']=False
        result['passed']=result['passed'] and native and result['active_skill_at_request']==active_skill
    return result


def control_identity(segment):
    """用途：身份只能来自本次成功接管后、退出前的捕获凭据，不能借用下一轮记录。"""
    entries=list(re.finditer(r'\[PBZBossControl\] enter success=true state=ACTIVE[^\r\n]*',segment))
    if not entries:return None
    tail=segment[entries[-1].end():]
    boundary=re.search(r'\[PBZBossControl\] (?:enter|exit|menu_exit|auto_exit) success=',tail)
    if boundary:tail=tail[:boundary.start()]
    worlds=re.findall(r'CONTROL_WORLD_ID=([^\r\n]+)',tail)
    rows=re.findall(r'CONTROL_PARTICIPANT=(player_controller|player|boss)\|([^|\r\n]+)\|address=(\d+)\|class=([^\r\n]+)',tail)
    if len(worlds)!=1 or len(rows)!=3 or len({row[0]for row in rows})!=3:return None
    identity={'world_id':worlds[0],'participants':{kind:{'name':name,'address':int(address),'class':cls}
              for kind,name,address,cls in rows}}
    if any(ref['address']<=0 for ref in identity['participants'].values()):return None
    return identity


def reload_retakeover_result(before,after,skill='skill_01'):
    """用途：同时要求旧会话恢复回收、新World身份、新主角接管、实际出招及新会话恢复。"""
    previous,current=control_identity(before),control_identity(after)
    old_restore,new_restore=restoration_result(before),restoration_result(after)
    retired=before.rfind('PBZ_REARM_RETIRE:PASS=')
    restored=max(before.rfind('[PBZBossControl] '+label+' success=true')for label in ('exit','menu_exit','auto_exit'))
    result={'before_identity':previous,'after_identity':current,'before_restoration':old_restore,
            'after_restoration':new_restore,'owned_retirement_preceded_reload':retired>restored>=0}
    if not previous or not current:return dict(result,passed=False,reason='complete captured identities required')
    result['same_research_session']=previous['world_id'].split('|',1)[0]==current['world_id'].split('|',1)[0]
    result['different_world']=previous['world_id']!=current['world_id']
    result['new_participants']=all(previous['participants'][key]!=current['participants'][key]
        and previous['participants'][key]['class']==current['participants'][key]['class']
        for key in ('player_controller','player','boss'))
    enter=after.rfind('[PBZBossControl] enter success=true')
    cycle=after[enter:]
    exit_event=re.search(r'\[PBZBossControl\] (?:exit|menu_exit|auto_exit) success=true',cycle)
    if exit_event:cycle=cycle[:exit_event.start()]
    result['skill_natural_finish']=bool(re.search(r'KEY_SKILL_END='+re.escape(skill)
        +r'\|peak=[1-9]\d*\|active=0\|natural=true\|',cycle))
    result['passed']=all((old_restore['passed'],new_restore['passed'],result['owned_retirement_preceded_reload'],
        result['same_research_session'],result['different_world'],result['new_participants'],result['skill_natural_finish']))
    return result


def classify_stop(segment):
    # 用途：保留自动收尾的真实取消证据，但不把它改写成玩家按键成功。
    return {'player_exit': bool(re.search(r'\[PBZBossControl\] exit success=true state=OFF', segment)),
            'menu_exit': bool(re.search(r'\[PBZBossControl\] menu_exit success=true state=OFF', segment)),
            'automatic_stop': bool(re.search(r'\[PBZBossControl\] stop success=true state=OFF', segment)),
            'faulted': 'state=FAULTED' in segment or 'PBZ_CONTROL_RESTORE:FAILED=' in segment}
