"""Run the installed SDR Challenge-inspired MUSIC/track example from a checkout."""
import sys
from airsim_rf.cli import main

if __name__=='__main__':
    sys.argv.insert(1,'track-demo')
    raise SystemExit(main())
