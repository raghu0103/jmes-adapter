import ast
from typing import Any, Dict


class SafeExpressionEvaluator:
    """
    Safe evaluator for YAML-defined formulas and conditions.
    Supports a restricted subset of Python expressions only.
    """

    ALLOWED_FUNCTIONS = {
        "min": min,
        "max": max,
        "round": round,
        "abs": abs,
        "int": int,
        "float": float,
        "str": str,
        "len": len,
    }

    ALLOWED_BINOPS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
    }

    ALLOWED_UNARYOPS = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
        ast.Not: lambda a: not a,
    }

    ALLOWED_CMPOPS = {
        ast.Eq: lambda a, b: a == b,
        ast.NotEq: lambda a, b: a != b,
        ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b,
        ast.Lt: lambda a, b: a < b,
        ast.LtE: lambda a, b: a <= b,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }

    def evaluate(self, expression: str, variables: Dict[str, Any]) -> Any:
        if not isinstance(expression, str):
            raise ValueError("Expression must be a string")

        expr = expression.strip()
        if expr.lower() == "true":
            return True
        if expr.lower() == "false":
            return False
        if expr.lower() == "null":
            return None

        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid expression syntax: {expression}") from e

        return self._eval_node(tree.body, variables)

    def _eval_node(self, node: ast.AST, variables: Dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            if node.id in variables:
                return variables[node.id]
            raise ValueError(f"Unknown variable '{node.id}' in expression")

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.ALLOWED_BINOPS:
                raise ValueError(f"Operator '{op_type.__name__}' not allowed")
            left = self._eval_node(node.left, variables)
            right = self._eval_node(node.right, variables)
            return self.ALLOWED_BINOPS[op_type](left, right)

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self.ALLOWED_UNARYOPS:
                raise ValueError(f"Unary operator '{op_type.__name__}' not allowed")
            operand = self._eval_node(node.operand, variables)
            return self.ALLOWED_UNARYOPS[op_type](operand)

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = True
                for value in node.values:
                    result = self._eval_node(value, variables)
                    if not result:
                        return result
                return result

            if isinstance(node.op, ast.Or):
                for value in node.values:
                    result = self._eval_node(value, variables)
                    if result:
                        return result
                return result

            raise ValueError(f"Boolean operator '{type(node.op).__name__}' not allowed")

        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, variables)

            for op, comparator in zip(node.ops, node.comparators):
                op_type = type(op)
                if op_type not in self.ALLOWED_CMPOPS:
                    raise ValueError(f"Comparison operator '{op_type.__name__}' not allowed")

                right = self._eval_node(comparator, variables)
                if not self.ALLOWED_CMPOPS[op_type](left, right):
                    return False
                left = right

            return True

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls are allowed")

            fn_name = node.func.id
            if fn_name not in self.ALLOWED_FUNCTIONS:
                raise ValueError(f"Function '{fn_name}' not allowed")

            args = [self._eval_node(arg, variables) for arg in node.args]
            return self.ALLOWED_FUNCTIONS[fn_name](*args)

        if isinstance(node, ast.List):
            return [self._eval_node(elt, variables) for elt in node.elts]

        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt, variables) for elt in node.elts)

        if isinstance(node, ast.Dict):
            return {
                self._eval_node(k, variables): self._eval_node(v, variables)
                for k, v in zip(node.keys, node.values)
            }

        raise ValueError(f"Unsupported expression node: {type(node).__name__}")