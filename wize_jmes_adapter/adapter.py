import asyncio
import copy
import jmespath
import logging
from .config_loader import load_config
from .http_client import call_api

logger = logging.getLogger(__name__)


class Adapter:
    def __init__(self, config_path):
        self.config = load_config(config_path)
        self._compiled = {}

    # -------------------------------
    # Utils
    # -------------------------------
    def _compile(self, key, expr):
        if key not in self._compiled:
            self._compiled[key] = jmespath.compile(expr)
        return self._compiled[key]

    def _normalize(self, result):
        if result is None:
            return []
        if isinstance(result, dict):
            return [result]
        return result

    def _get_operation(self, operation):
        ops = self.config.get("operations", {})
        if operation not in ops:
            raise ValueError(f"Operation '{operation}' not found in config")
        return ops[operation]

    def _resolve(self, expr, item, results, context):
        if not isinstance(expr, str):
            return expr

        if expr.startswith("item."):
            return jmespath.search(expr[5:], item)

        if expr.startswith("results."):
            return jmespath.search(expr[8:], results)

        if expr.startswith("context."):
            return jmespath.search(expr[8:], context)

        return expr

    def _build_context(self, base, mapping, item, results):
        ctx = copy.deepcopy(base)
        for k, v in (mapping or {}).items():
            value = self._resolve(v, item, results, base)

            if value is None:
                raise ValueError(f"Context mapping failed for key '{k}' (got None)")

            ctx[k] = value
        return ctx

    # -------------------------------
    # Auth Handler
    # -------------------------------
    async def _handle_auth(self, operation, context, results):
        auth_cfg = self.config.get("auth")
        if not auth_cfg or not auth_cfg.get("enabled"):
            return context

        if operation in auth_cfg.get("skip_for", []):
            return context

        # skip if already present
        if all(context.get(k) for k in auth_cfg.get("result_map", {})):
            return context

        auth_ctx = self._build_context(
            context,
            auth_cfg.get("context_map"),
            None,
            results
        )

        auth_result = await self.run(auth_cfg["operation"], auth_ctx, results)

        enriched = copy.deepcopy(context)
        for k, expr in auth_cfg["result_map"].items():
            enriched[k] = jmespath.search(expr, auth_result)

        return enriched

    # -------------------------------
    # Operation Execution
    # -------------------------------
    async def _run_transform(self, operation, op, context, results):
        source = op["operation"].get("source", "results")

        payload = jmespath.search(source, {
            "context": context,
            "results": results
        })

        expr = op["response"]["expression"]
        result = self._compile(operation, expr).search(payload)

        return self._normalize(result)

    async def _run_single(self, operation, op, context, results):
        context = await self._handle_auth(operation, context, results)

        op_cfg = op.get("operation", {})
        op_type = op_cfg.get("type", "REST").upper()

        if op_type == "TRANSFORM":
            return await self._run_transform(operation, op, context, results)

        response = await call_api(op_cfg, context)

        expr = op["response"]["expression"]
        result = self._compile(operation, expr).search(response)

        return self._normalize(result)

    # -------------------------------
    # Workflow Execution
    # -------------------------------
    async def _run_step(self, step, results, context):
        name = step["name"]
        operation = step["operation"]

        ctx = self._build_context(context, step.get("context_map"), None, results)

        result = await self.run(operation, ctx, results)

        return name, result

    async def _run_parallel(self, steps, results, context):
        tasks = [self._run_step(s, results, context) for s in steps]
        out = await asyncio.gather(*tasks)
        return dict(out)

    async def _run_for_each(self, step, results, context):
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
        return flattened

    async def _run_workflow(self, operation, op, context):
        steps = op["workflow"]["steps"]
        results = {}

        for step in steps:

            # ---------------- parallel_group
            if "parallel_group" in step:
                results.update(await self._run_parallel(step["parallel_group"], results, context))
                continue

            # ---------------- for_each
            if "for_each" in step:
                name = step["name"]
                results[name] = await self._run_for_each(step, results, context)
                continue

            # ---------------- normal step
            name, res = await self._run_step(step, results, context)
            results[name] = res

        expr = op["workflow"].get("response", {}).get("expression")

        if expr:
            final = self._compile(operation, expr).search(results)
        else:
            final = results

        return self._normalize(final)

    # -------------------------------
    # Entry Point
    # -------------------------------
    async def run(self, operation, context=None, results=None):
        context = context or {}
        results = results or {}

        op = self._get_operation(operation)

        if "workflow" in op:
            return await self._run_workflow(operation, op, context)

        return await self._run_single(operation, op, context, results)