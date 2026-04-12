from typing import Any, Dict, List

from .safe_eval import SafeExpressionEvaluator


class FunctionEngine:
    def __init__(self, config: Dict[str, Any]):
        self.functions = config.get("functions", {})
        self.evaluator = SafeExpressionEvaluator()

    def execute(self, func_name: str, args: List[Any]) -> Any:
        func_cfg = self.functions.get(func_name)

        if not func_cfg:
            raise ValueError(f"Function '{func_name}' is not defined in YAML config")

        func_type = func_cfg.get("type")
        params = func_cfg.get("params", ["value"])

        if len(args) != len(params):
            raise ValueError(
                f"Function '{func_name}' expects {len(params)} args ({params}) but got {len(args)}"
            )

        variables = dict(zip(params, args))

        if func_type == "conditional":
            rules = func_cfg.get("rules", [])
            for rule in rules:
                condition = rule.get("when", rule.get("condition", "true"))
                if self.evaluator.evaluate(condition, variables):
                    return rule.get("value")
            raise ValueError(f"No matching conditional rule for function '{func_name}'")

        if func_type == "formula":
            expression = func_cfg.get("expression")
            if not expression:
                raise ValueError(f"Formula function '{func_name}' missing 'expression'")
            return self.evaluator.evaluate(expression, variables)

        if func_type == "mapping":
            mappings = func_cfg.get("map", func_cfg.get("mapping", {}))
            key = args[0]
            if str(key) in mappings:
                return mappings[str(key)]
            if key in mappings:
                return mappings[key]
            return func_cfg.get("default")

        raise ValueError(f"Unsupported function type '{func_type}' for function '{func_name}'")