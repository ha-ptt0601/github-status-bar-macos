import os

# Never read the developer's real ~/.config/chip/config.json while testing.
os.environ["CHIP_CONFIG"] = os.path.join(os.path.dirname(__file__), "no-such-config.json")
os.environ["CHIP_CLAUDE_PROJECTS"] = os.path.join(os.path.dirname(__file__), "no-such-projects")  # never read real sessions
