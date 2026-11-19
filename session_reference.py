"""Python MIRROR of HD_SessionContains (HD_DataAudit.mqh). Used only to check the ALGORITHM and the
test vectors; it does NOT test the MQL5 code. The same cases are hardcoded in GatesFX_HD_UnitTests.mq5."""


def contains(sessions, dow, sod):
    """sessions: {dow: [(from_s, to_s), ...]}; dow 0=Sunday."""
    if not (0 <= dow <= 6 and 0 <= sod <= 86399):
        return False
    for f, t in sessions.get(dow, []):
        t = min(t, 86400)
        if t > f:
            if f <= sod < t:
                return True
        elif t < f:
            if sod >= f:
                return True
    pd = (dow + 6) % 7
    for f, t in sessions.get(pd, []):
        if t < f and sod < t:
            return True
    return False
