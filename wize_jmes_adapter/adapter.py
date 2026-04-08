import jmespath
import logging
from .config_loader import load_config
from .http_client import call_api
import asyncio

logger = logging.getLogger(__name__)


class Adapter:

    def __init__(self, config_path):
        self.config = load_config(config_path)
        self._compiled_expressions = {}

    # -------------------------------
    # Get operation config
    # -------------------------------
    def _get_operation(self, operation):
        operations = self.config.get("operations", {})
        if operation not in operations:
            raise ValueError(f"Operation '{operation}' not found in config")
        return operations[operation]

    # -------------------------------
    # Compile & cache JMESPath
    # -------------------------------
    def _get_compiled_expression(self, operation, expression):
        key = f"{operation}:{expression}"

        if key not in self._compiled_expressions:
            self._compiled_expressions[key] = jmespath.compile(expression)

        return self._compiled_expressions[key]

    # -------------------------------
    # Apply selector (GENERIC)
    # -------------------------------
    def _apply_selector(self, response, selector, context):
        if not selector:
            return response

        try:
            selector_str = selector

            # Inject variables like ${ticket_id}
            if isinstance(selector_str, str):
                for key, value in context.items():
                    selector_str = selector_str.replace(f"${{{key}}}", str(value))
                # If variable not resolved → skip selector
                if "${" in selector_str:
                    logger.debug(
                        "Skipping selector due to missing context variable: %s",
                        selector
                    )
                    return response
            else:
                return response

            logger.debug("Applying selector: %s", selector_str)

            # Fast path: direct key access
            if isinstance(response, dict) and "." not in selector_str and selector_str in response:
                return response.get(selector_str, [])

            # Fallback: JMESPath selector
            # return jmespath.search(selector_str, response)
            selected = jmespath.search(selector_str, response)
            return selected if selected is not None else response

        except Exception as e:
            logger.warning("Selector failed, returning original response: %s", e)
            return response

    # -------------------------------
    # Main execution
    # -------------------------------

    async def run(self, operation, context=None, raw_response=None):
        context = context or {}

        try:
            op = self._get_operation(operation)

            # ===============================
            # MULTI-STEP EXECUTION
            # ===============================
            if "steps" in op:
                logger.debug("Executing multi-step operation: %s", operation)

                results = {}
                parallel_steps = []
                parallel_names = []

                for step in op["steps"]:
                    step_name = step["name"]
                    step_operation = step["operation"]
                    condition = step.get("condition")

                    # Steps with condition depend on previous results,
                    # so execute them sequentially.
                    if condition:
                        if not results:
                            logger.debug("Skipping conditional step %s due to missing dependencies", step_name)
                            continue
                        try:
                            condition_result = jmespath.search(condition, results)
                            logger.debug(
                                "Condition for step %s -> %s = %s",
                                step_name, condition, condition_result
                            )

                            if not condition_result:
                                logger.debug("Skipping step: %s", step_name)
                                continue

                        except Exception as e:
                            logger.warning(
                                "Condition evaluation failed for step %s: %s",
                                step_name,
                                e,
                            )
                            continue

                        logger.debug("Running conditional step sequentially: %s", step_name)
                        step_result = await self.run(step_operation, context=context)
                        results[step_name] = step_result
                        continue

                    # Steps without condition are treated as independent
                    # and can be executed in parallel.
                    parallel_steps.append(
                        asyncio.create_task(self.run(step_operation, context=context))
                    )
                    parallel_names.append(step_name)

                # Run all independent steps in parallel
                if parallel_steps:
                    logger.debug(
                        "Running %d parallel steps for operation: %s",
                        len(parallel_steps),
                        operation,
                    )
                    parallel_results = await asyncio.gather(*parallel_steps)

                    for step_name, step_result in zip(parallel_names, parallel_results):
                        results[step_name] = step_result

                # Apply final transformation to collected step results
                expression = op.get("response", {}).get("expression")

                if expression:
                    compiled = self._get_compiled_expression(operation, expression)
                    result = compiled.search(results)
                else:
                    result = results

                logger.debug(
                    "Multi-step JMESPath result for %s: %s",
                    operation,
                    str(result)[:500],
                )

                if isinstance(result, dict):
                    result = [result]

                return result

            # ===============================
            # NORMAL SINGLE OPERATION
            # ===============================
            if raw_response is not None:
                response = raw_response
                logger.debug("Using raw_response for operation: %s", operation)
            else:
                operation_config = op.get("operation")
                if not operation_config:
                    raise ValueError(f"No operation config found for '{operation}'")

                logger.debug("Calling API for operation: %s", operation)
                response = await call_api(operation_config, context)

            selector = op.get("response", {}).get("selector")
            response = self._apply_selector(response, selector, context)

            expression = op.get("response", {}).get("expression")
            if not expression:
                raise ValueError(f"No JMESPath expression found for operation '{operation}'")

            compiled = self._get_compiled_expression(operation, expression)
            result = compiled.search(response)

            logger.debug("JMESPath result for %s: %s", operation, str(result)[:500])

            if isinstance(result, dict):
                result = [result]

            return result

        except Exception as e:
            logger.exception("Error executing operation '%s'", operation)
            raise RuntimeError(f"[Adapter:{operation}] {str(e)}")