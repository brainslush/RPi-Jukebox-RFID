"""Enable direct plugin imports for alarmclock tests (no jukebox daemon running)."""
import sys
import os
sys.path.append(os.path.abspath('src/jukebox'))

import jukebox.plugs as plugs
plugs.ALLOW_DIRECT_IMPORTS = True
