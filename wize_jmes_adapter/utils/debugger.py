import pprint


class Debugger:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def step(self, name: str):
        if self.enabled:
            print(f"\n🚀 STEP: {name}")

    def log(self, label: str, data):
        if self.enabled:
            print(f"\n🔍 {label}")
            pprint.pprint(data, width=120, sort_dicts=False)