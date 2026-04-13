import httpx
import logging
from tenacity import retry, stop_after_attempt, wait_fixed

from .utils.template_engine import TemplateEngine

logger = logging.getLogger(__name__)


def build_headers(details, context, engine, item=None, results=None):
    headers = {}

    for section in ["required", "runtime", "optional"]:
        for k, v in details.get("headers", {}).get(section, {}).items():
            val = engine.render(v, item or {}, results or {}, context)
            if val is not None:
                headers[k] = val

    return headers


def build_data(details, context, engine, item=None, results=None):
    # Ensure TemplateEngine resolves pan_number correctly from context
    resolved_data = engine.render(details.get("data", {}), item or {}, results or {}, context)

    # Debugging: Log resolved data to make sure pan_number is correctly resolved
    logger.debug(f"Resolved Data: {resolved_data}")
    
    return resolved_data


def build_query_params(details, context, engine, item=None, results=None):
    return {
        k: engine.render(v, item or {}, results or {}, context)
        for k, v in details.get("queryParams", {}).items()
    }


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def _make_request(client, method, url, headers, params, data):
    response = await client.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=data if method in ["POST", "PUT", "PATCH"] else None
    )

    response.raise_for_status()
    return response


async def call_api(operation_config, context, item=None, results=None):
    details = operation_config["details"]
    engine = TemplateEngine(config={})

    method = details["method"]
    url = engine.render(details["route"], item or {}, results or {}, context)

    headers = build_headers(details, context, engine, item, results)
    data = build_data(details, context, engine, item, results)
    params = build_query_params(details, context, engine, item, results)

    async with httpx.AsyncClient(timeout=details.get("timeout", 10)) as client:
        response = await _make_request(client, method, url, headers, params, data)

        try:
            return response.json()
        except Exception:
            return response.text