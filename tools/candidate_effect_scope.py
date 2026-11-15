"""Developer actions must stay within the independently bounded local training area."""
import copy
import math
import re

LOCAL_DISPLACEMENT_CM = 3000


def local_effect(result, text, limit=LOCAL_DISPLACEMENT_CM):
    assert limit == LOCAL_DISPLACEMENT_CM, 'Fixed local developer bound required'
    result = copy.deepcopy(result)
    distances = [float(v) for v in re.findall(r'CONTROLLED_BOSS_POSITION_DELTA=([^\s|]+)', text)]
    natural = result.get('natural_completion')
    if natural:
        distances.append(natural['distance'])
    passed = bool(distances) and all(math.isfinite(v) and 0 <= v <= limit for v in distances)
    result['local_displacement_verified'] = passed
    result['local_displacement_limit_cm'] = limit
    result['observed_displacements_cm'] = distances
    if not passed:
        result['natural_completion'] = None
        result['active_cancel_and_restoration'] = False
    return result
