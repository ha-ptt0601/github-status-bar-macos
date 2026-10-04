import os

# Never read the developer's real ~/.config/chip/config.json while testing.
os.environ["CHIP_CONFIG"] = os.path.join(os.path.dirname(__file__), "no-such-config.json")
