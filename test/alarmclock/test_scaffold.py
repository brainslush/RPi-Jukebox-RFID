import sys
import os
sys.path.append(os.path.abspath('src/jukebox'))


def test_pydantic_importable():
    """pydantic v2 is installed"""
    import pydantic
    assert int(pydantic.VERSION.split('.')[0]) >= 2


def test_alarmclock_module_importable():
    """alarmclock plugin module can be imported"""
    import jukebox.plugs as plugs
    plugs.ALLOW_DIRECT_IMPORTS = True
    import components.alarmclock
    plugs.ALLOW_DIRECT_IMPORTS = False
    assert components.alarmclock is not None
