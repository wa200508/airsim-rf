"""Legacy math re-exports; implementation belongs to wa200508/DF-Skill."""
try:
    from df_skill.music import C, PhysicalULA, estimate_bearing, read_arrays, frequency_psd, spatial_spectrum
except ImportError as error:
    raise ImportError("Direction finding math moved to DF-Skill; install airsim-rf[tracking]") from error
