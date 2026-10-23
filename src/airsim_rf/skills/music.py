"""Legacy import/CLI shim for the external Direction Finding RF Skill.

The application is maintained at https://github.com/wa200508/DF-Skill.
Install airsim-rf[tracking] for legacy Python consumers; the live dashboard runs
the independently published DF-Skill container.
"""
try:
    from df_skill.app import DirectionFindingSkill as MusicSkill, main, start_control
except ImportError as error:
    raise ImportError("Direction Finding RF Skill moved to wa200508/DF-Skill; install airsim-rf[tracking]") from error

if __name__ == '__main__': main()
