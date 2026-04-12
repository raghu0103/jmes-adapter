import re
from typing import Any, Dict, List, Optional

import jmespath

from .debugger import Debugger
from .function_engine import FunctionEngine


class TemplateEngine:
    PLACEHOLDER_PATTERN = re.compile(r"\$\{([^}]+)\}")
    FUNCTION_CALL_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$")

    def __init__(self, config: Dict[str, Any], debugger: Optional[Debugger] = None):
        self.config = config
        self.func_engine = FunctionEngine(config)
        self.debugger = debugger or Debugger(False)

    def render(self, obj: Any, item: Any, results: Dict[str, Any], context: Dict[str, Any]) -> Any:
        rendered = self._render_structure(obj, item, results, context)
        self.debugger.log("TEMPLATE OUTPUT", rendered)
        return rendered

    def _is_number_literal(self, value: str) -> bool:
        try:
            float(value)
            return True
        except Exception:
            return False

    def _parse_literal(self, value: str) -> Any:
        v = value.strip()

        if len(v) >= 2 and ((v[0] == "'" and v[-1] == "'") or (v[0] == '"' and v[-1] == '"')):
            return v[1:-1]

        if v.lower() == "true":
            return True

        if v.lower() == "false":
            return False

        if v.lower() == "null":
            return None

        if self._is_number_literal(v):
            num = float(v)
            return int(num) if num.is_integer() else num

        return v

    def _resolve_reference(self, expr: str, item: Any, results: Dict[str, Any], context: Dict[str, Any]) -> Any:
        expr = expr.strip()

        if expr.startswith("item."):
            return jmespath.search(expr[5:], item)

        if expr.startswith("results."):
            return jmespath.search(expr[8:], results)

        if expr.startswith("context."):
            return jmespath.search(expr[8:], context)

        return None

    def _split_args(self, args_str: str) -> List[str]:
        args = []
        current = []
        depth = 0
        in_single = False
        in_double = False

        for ch in args_str:
            if ch == "'" and not in_double:
                in_single = not in_single
                current.append(ch)
                continue

            if ch == '"' and not in_single:
                in_double = not in_double
                current.append(ch)
                continue

            if not in_single and not in_double:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                elif ch == "," and depth == 0:
                    args.append("".join(current).strip())
                    current = []
                    continue

            current.append(ch)

        if current:
            args.append("".join(current).strip())

        return [a for a in args if a]

    def _resolve_scalar(self, expr: Any, item: Any, results: Dict[str, Any], context: Dict[str, Any]) -> Any:
        if not isinstance(expr, str):
            return expr

        stripped = expr.strip()

        direct_ref = self._resolve_reference(stripped, item, results, context)
        if direct_ref is not None:
            self.debugger.log(f"RESOLVED REF: {stripped}", direct_ref)
            return direct_ref

        full_match = self.PLACEHOLDER_PATTERN.fullmatch(stripped)
        if full_match:
            inner = full_match.group(1).strip()
            ref_value = self._resolve_reference(inner, item, results, context)
            if ref_value is not None:
                self.debugger.log(f"RESOLVED PLACEHOLDER: {stripped}", ref_value)
                return ref_value
            parsed = self._parse_literal(inner)
            self.debugger.log(f"PARSED PLACEHOLDER LITERAL: {stripped}", parsed)
            return parsed

        fn_match = self.FUNCTION_CALL_PATTERN.match(stripped)
        if fn_match:
            func_name = fn_match.group(1)
            raw_args = fn_match.group(2).strip()
            args = []

            if raw_args:
                for raw_arg in self._split_args(raw_args):
                    ref_value = self._resolve_reference(raw_arg, item, results, context)
                    if ref_value is not None:
                        args.append(ref_value)
                        continue

                    nested_match = self.FUNCTION_CALL_PATTERN.match(raw_arg)
                    if nested_match:
                        args.append(self._resolve_scalar(raw_arg, item, results, context))
                        continue

                    args.append(self._parse_literal(raw_arg))

            result = self.func_engine.execute(func_name, args)
            self.debugger.log(f"FUNCTION {func_name}", {"args": args, "result": result})
            return result

        if self.PLACEHOLDER_PATTERN.search(stripped):
            def repl(match):
                inner = match.group(1).strip()
                ref_value = self._resolve_reference(inner, item, results, context)
                if ref_value is None:
                    return match.group(0)
                return str(ref_value)

            replaced = self.PLACEHOLDER_PATTERN.sub(repl, stripped)
            self.debugger.log(f"INTERPOLATED STRING: {stripped}", replaced)
            return replaced

        return expr

    def _render_structure(self, obj: Any, item: Any, results: Dict[str, Any], context: Dict[str, Any]) -> Any:
        if isinstance(obj, dict):
            return {
                k: self._render_structure(v, item, results, context)
                for k, v in obj.items()
            }

        if isinstance(obj, list):
            return [self._render_structure(v, item, results, context) for v in obj]

        return self._resolve_scalar(obj, item, results, context)