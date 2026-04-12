import asyncio
import copy
import logging
from typing import Any, Dict, List, Optional

import jmespath

from .config_loader import load_config
from .http_client import call_api
from .utils.debugger import Debugger
from .utils.jmes_utils import JMESHelper
from .utils.template_engine import TemplateEngine
from .utils.validator import ConfigValidator

logger = logging.getLogger(__name__)


class Adapter:
    def __init__(self, config_path, debug: bool = False):
        self.config = load_config(config_path)
        ConfigValidator(self.config).validate()

        self.debugger = Debugger(debug)
        self.jmes = JMESHelper()
        self.template = TemplateEngine(self.config, self.debugger)

    # -------------------------------
    # Utils
    # -------------------------------
    def _normalize(self, result: Any) -> List[Any]:
        if result is None:
            return []
        if isinstance(result, dict):
            return [result]
        return result

    def _get_operation(self, operation: str) -> Dict[str, Any]:
        ops = self.config.get("operations", {})
        if operation not in ops:
            raise ValueError(f"Operation '{operation}' not found in config")
        return ops[operation]

    def _resolve(self, expr: Any, item: Any, results: Dict[str, Any], context: Dict[str, Any]) -> Any:
        if not isinstance(expr, str):
            return expr

        if expr.startswith("item."):
            return jmespath.search(expr[5:], item)

        if expr.startswith("results."):
            return jmespath.search(expr[8:], results)

        if expr.startswith("context."):
            return jmespath.search(expr[8:], context)

        return expr

    def _build_context(self, base: Dict[str, Any], mapping: Optional[Dict[str, Any]], item: Any, results: Dict[str, Any]) -> Dict[str, Any]:
        ctx = copy.deepcopy(base)

        for k, v in (mapping or {}).items():
            value = self.template._resolve_scalar(v, item, results, base)

            if value is None:
                raise ValueError(f"Context mapping failed for key '{k}' (got None)")

            ctx[k] = value

        self.debugger.log("BUILT CONTEXT", ctx)
        return ctx

    # -------------------------------
    # Auth Handler
    # -------------------------------
    async def _handle_auth(self, operation: str, context: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
        auth_cfg = self.config.get("auth")
        if not auth_cfg or not auth_cfg.get("enabled"):
            return context

        if operation in auth_cfg.get("skip_for", []):
            return context

        if all(context.get(k) for k in auth_cfg.get("result_map", {})):
            return context

        auth_ctx = self._build_context(
            context,
            auth_cfg.get("context_map"),
            None,
            results
        )

        auth_result = await self.run(auth_cfg["operation"], auth_ctx, results)

        if isinstance(auth_result, list) and len(auth_result) == 1:
            auth_result_data = auth_result[0]
        else:
            auth_result_data = auth_result

        enriched = copy.deepcopy(context)
        for k, expr in auth_cfg["result_map"].items():
            enriched[k] = jmespath.search(expr, auth_result_data)

        self.debugger.log("AUTH ENRICHED CONTEXT", enriched)
        return enriched

    # -------------------------------
    # Operation Execution
    # -------------------------------
    async def _run_transform(self, operation: str, op: Dict[str, Any], context: Dict[str, Any], results: Dict[str, Any]) -> List[Any]:
        source = op["operation"].get("source", "results")

        payload = jmespath.search(source, {
            "context": context,
            "results": results
        })

        self.debugger.log("TRANSFORM PAYLOAD", payload)

        response_cfg = op.get("response", {})
        if "template" in response_cfg:
            result = self.template.render(response_cfg["template"], None, payload, context)
            return self._normalize(result)

        expr = response_cfg["expression"]
        result = self.jmes.search(operation, expr, payload)

        self.debugger.log("TRANSFORM RESULT", result)
        return self._normalize(result)

    async def _run_single(self, operation: str, op: Dict[str, Any], context: Dict[str, Any], results: Dict[str, Any]) -> List[Any]:
        self.debugger.step(operation)

        context = await self._handle_auth(operation, context, results)

        op_cfg = copy.deepcopy(op.get("operation", {}))
        op_type = op_cfg.get("type", "REST").upper()

        if op_type == "TRANSFORM":
            return await self._run_transform(operation, op, context, results)

        rendered_op_cfg = self.template.render(op_cfg, None, results, context)
        self.debugger.log("RENDERED OP CONFIG", rendered_op_cfg)

        response = await call_api(rendered_op_cfg, context)
        self.debugger.log("API RESPONSE", response)

        response_cfg = op.get("response", {})
        if "template" in response_cfg:
            result = self.template.render(response_cfg["template"], None, response, context)
            return self._normalize(result)

        expr = response_cfg["expression"]
        result = self.jmes.search(operation, expr, response)

        self.debugger.log("JMES RESULT", result)
        return self._normalize(result)

    # -------------------------------
    # Workflow Execution
    # -------------------------------
    async def _run_step(self, step: Dict[str, Any], results: Dict[str, Any], context: Dict[str, Any]):
        name = step["name"]
        operation = step["operation"]

        self.debugger.step(name)

        ctx = self._build_context(context, step.get("context_map"), None, results)
        result = await self.run(operation, ctx, results)

        self.debugger.log(f"STEP RESULT: {name}", result)
        return name, result

    async def _run_parallel(self, steps: List[Dict[str, Any]], results: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        tasks = [self._run_step(s, results, context) for s in steps]
        out = await asyncio.gather(*tasks)
        parallel_results = dict(out)
        self.debugger.log("PARALLEL GROUP RESULT", parallel_results)
        return parallel_results

    async def _run_for_each(self, step: Dict[str, Any], results: Dict[str, Any], context: Dict[str, Any]) -> List[Any]:
        collection_name = step["for_each"]
        collection = results.get(collection_name)

        if collection is None:
            raise ValueError(f"for_each target '{collection_name}' not found in results")

        if not isinstance(collection, list):
            raise ValueError(f"for_each target '{collection_name}' must be a list")

        async def run_one(item):
            ctx = self._build_context(context, step.get("context_map"), item, results)
            return await self.run(step["operation"], ctx, results)

        if step.get("parallel", True):
            tasks = [run_one(item) for item in collection]
            outputs = await asyncio.gather(*tasks)
        else:
            outputs = []
            for item in collection:
                outputs.append(await run_one(item))

        flattened = [x for sub in outputs for x in sub]
        self.debugger.log("FOR_EACH RESULT", flattened)
        return flattened

    async def _run_workflow(self, operation: str, op: Dict[str, Any], context: Dict[str, Any]) -> List[Any]:
        steps = op["workflow"]["steps"]
        results = {}

        for step in steps:
            if "parallel_group" in step:
                results.update(await self._run_parallel(step["parallel_group"], results, context))
                continue

            if "for_each" in step:
                name = step["name"]
                results[name] = await self._run_for_each(step, results, context)
                continue

            name, res = await self._run_step(step, results, context)
            results[name] = res

        self.debugger.log("WORKFLOW RESULTS", results)

        response_cfg = op.get("response", {}) or op.get("workflow", {}).get("response", {})

        if "template" in response_cfg:
            final = self.template.render(response_cfg["template"], None, {"results": results}, context)
            self.debugger.log("FINAL TEMPLATE OUTPUT", final)
            return self._normalize(final)

        expr = response_cfg.get("expression")
        if expr:
            final = self.jmes.search(operation, expr, results)
        else:
            final = results

        self.debugger.log("FINAL WORKFLOW OUTPUT", final)
        return self._normalize(final)

    # -------------------------------
    # Entry Point
    # -------------------------------
    async def run(
        self,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
        results: Optional[Dict[str, Any]] = None,
        debug: Optional[bool] = None,
    ):
        context = context or {}
        results = results or {}

        if debug is not None:
            self.debugger.set_enabled(debug)

        op = self._get_operation(operation)

        if "workflow" in op:
            return await self._run_workflow(operation, op, context)

        return await self._run_single(operation, op, context, results)