"""新装配的初始化与交互期限；绝不续期已签发凭据。"""
import math

INITIALIZATION_SECONDS = 120
INTERACTIVE_SECONDS = 600
CLEANUP_SECONDS = 20
SESSION_CLEANUP_SECONDS = 30


def issue_expiry(now, session_deadline, *, practice=False, remote=False):
    if not (math.isfinite(now) and math.isfinite(session_deadline)):
        raise ValueError('Finite lease timestamps required')
    lifetime = (INITIALIZATION_SECONDS + INTERACTIVE_SECONDS + CLEANUP_SECONDS
                if practice else 90 if remote else 45)
    expiry = min(int(now) + lifetime, int(session_deadline) - SESSION_CLEANUP_SECONDS)
    if expiry <= now:
        raise ValueError('Session has insufficient remaining lease')
    return expiry
