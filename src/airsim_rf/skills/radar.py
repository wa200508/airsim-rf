"""Compatibility shim for the independently maintained Radar RF Skill.

Implementation: https://github.com/wa200508/Radar-skill.
Install airsim-rf[radar] for legacy Python imports. The dashboard runs its
separately published CPU container.
"""
try:
    from radar_skill.app import RadarSkill,main
    from radar_skill.processing import range_doppler
except ImportError as error:
    raise ImportError('Radar RF Skill moved to wa200508/Radar-skill; install airsim-rf[radar]') from error

if __name__=='__main__':main()
