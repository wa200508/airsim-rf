"""Compatibility entry point for the ground-only repository example.

Use `airsim-rf example` for the installed shared-geometry workflow.
"""
from airsim_rf.example import main, prepare

if __name__ == '__main__':
    import sys
    if '--geometry' not in sys.argv:
        sys.argv.extend(['--geometry', 'ground'])
    main()
