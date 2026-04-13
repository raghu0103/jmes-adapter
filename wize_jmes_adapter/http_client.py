import httpx
import logging
from tenacity import retry, stop_after_attempt, wait_fixed
import re
from wize_jmes_adapter.template_engine import TemplateEngine

logger = logging.getLogger(__name__)


def build_headers(details, context, engine):
    headers = {}

    for section in ["required", "runtime", "optional"]:
        for k, v in details.get("headers", {}).get(section, {}).items():
            # val = inject(v, context)
            val = engine.render(v, {}, {}, context)

            # skip None optional headers
            if val is not None:
                headers[k] = val

    return headers

def build_data(details, context, engine, item=None, results=None):
    return engine.render(details.get("data", {}), item or {}, results or {}, context)


def build_query_params(details, context, engine, item=None, results=None):
    return {
        k: engine.render(v, item or {}, results or {}, context)
        for k, v in details.get("queryParams", {}).items()
    }


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def _make_request(client, method, url, headers, params, data):
    logger.debug("Calling API %s %s", method, url)

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

    method = details["method"]
    engine = TemplateEngine(config={})

    headers = build_headers(details, context, engine)
    data = build_data(details, context, engine, item, results)
    params = build_query_params(details, context, engine, item, results)
    url = engine.render(details["route"], item or {}, results or {}, context)

    timeout = details.get("timeout", 10)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:

            response = await _make_request(
                client,
                method,
                url,
                headers,
                params,
                data
            )

            logger.debug("Response status: %s", response.status_code)
            # print("\n===== RAW RESPONSE =====")
            # print("Status:", response.status_code)
            # print("Text:", response.text[:1000])
            # print("========================\n")
            try:
                return response.json()
            except Exception:
                # fallback for plain text (like SMAX auth token)
                return response.text

    except httpx.HTTPStatusError as e:
        logger.error("HTTP error: %s - %s", e.response.status_code, e.response.text)
        raise

    except Exception as e:
        logger.exception("API call failed")
        raise