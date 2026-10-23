"""Compatibility launch/import alias. The source-agnostic application is skills.music."""
from .skills.music import MusicSkill as Skill, main, start_control

if __name__=='__main__':main()
