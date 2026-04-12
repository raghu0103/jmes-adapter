import jmespath
from typing import Any, Dict


class JMESHelper:
    def __init__(self):
        self._compiled: Dict[str, Any] = {}

    def compile(self, key: str, expr: str):
        if key not in self._compiled:
            self._compiled[key] = jmespath.compile(expr)
        return self._compiled[key]

    def search(self, key: str, expr: str, data: Any) -> Any:
        return self.compile(key, expr).search(data)