from typing import Any, Dict


class ConfigValidator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def validate(self):
        self._validate_operations()
        self._validate_functions()
        self._validate_auth()

    def _validate_operations(self):
        ops = self.config.get("operations")
        if not ops or not isinstance(ops, dict):
            raise ValueError("Config must contain a non-empty 'operations' dictionary")

        for name, op in ops.items():
            if not isinstance(op, dict):
                raise ValueError(f"Operation '{name}' must be a dictionary")

            if "operation" not in op and "workflow" not in op:
                raise ValueError(f"Operation '{name}' must have 'operation' or 'workflow'")

            if "operation" in op:
                if not isinstance(op["operation"], dict):
                    raise ValueError(f"Operation '{name}.operation' must be a dictionary")

                op_type = op["operation"].get("type")
                if op_type is None:
                    raise ValueError(f"Operation '{name}.operation.type' is required")

                if "response" not in op:
                    raise ValueError(f"Operation '{name}' must define 'response'")

            if "workflow" in op:
                wf = op["workflow"]
                if not isinstance(wf, dict):
                    raise ValueError(f"Operation '{name}.workflow' must be a dictionary")

                steps = wf.get("steps")
                if not isinstance(steps, list):
                    raise ValueError(f"Operation '{name}.workflow.steps' must be a list")

                for idx, step in enumerate(steps):
                    if not isinstance(step, dict):
                        raise ValueError(f"Workflow step {idx} in '{name}' must be a dictionary")

                    if "parallel_group" in step:
                        if not isinstance(step["parallel_group"], list):
                            raise ValueError(f"'parallel_group' in '{name}' step {idx} must be a list")
                        continue

                    if "for_each" in step:
                        if "name" not in step or "operation" not in step:
                            raise ValueError(
                                f"'for_each' step {idx} in '{name}' must define 'name' and 'operation'"
                            )
                        continue

                    if "name" not in step or "operation" not in step:
                        raise ValueError(
                            f"Workflow step {idx} in '{name}' must define 'name' and 'operation'"
                        )

    def _validate_functions(self):
        functions = self.config.get("functions", {})
        if not isinstance(functions, dict):
            raise ValueError("'functions' must be a dictionary")

        for name, fn in functions.items():
            if not isinstance(fn, dict):
                raise ValueError(f"Function '{name}' must be a dictionary")

            fn_type = fn.get("type")
            if not fn_type:
                raise ValueError(f"Function '{name}' missing 'type'")

            if fn_type == "conditional":
                rules = fn.get("rules")
                if not isinstance(rules, list) or not rules:
                    raise ValueError(f"Conditional function '{name}' must define non-empty 'rules'")

            elif fn_type == "formula":
                if not fn.get("expression"):
                    raise ValueError(f"Formula function '{name}' missing 'expression'")

            elif fn_type == "mapping":
                mapping = fn.get("map", fn.get("mapping"))
                if not isinstance(mapping, dict):
                    raise ValueError(f"Mapping function '{name}' must define 'map' or 'mapping' dict")

            else:
                raise ValueError(f"Function '{name}' has unsupported type '{fn_type}'")

    def _validate_auth(self):
        auth = self.config.get("auth")
        if not auth:
            return

        if not isinstance(auth, dict):
            raise ValueError("'auth' must be a dictionary")

        if auth.get("enabled") and not auth.get("operation"):
            raise ValueError("Enabled auth config must define 'operation'")