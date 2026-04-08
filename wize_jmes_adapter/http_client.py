import httpx
import logging
from tenacity import retry, stop_after_attempt, wait_fixed
import re

logger = logging.getLogger(__name__)


def inject(value, context):
    if isinstance(value, str):
        matches = re.findall(r"\$\{(.*?)\}", value)

        for match in matches:
            replacement = str(context.get(match, ""))
            value = value.replace(f"${{{match}}}", replacement)

    return value


def build_headers(details, context):
    headers = {}

    for section in ["required", "runtime", "optional"]:
        for k, v in details.get("headers", {}).get(section, {}).items():
            val = inject(v, context)

            # skip None optional headers
            if val is not None:
                headers[k] = val

    return headers


def build_data(details, context):
    return {
        k: inject(v, context)
        for k, v in details.get("data", {}).items()
    }


def build_query_params(details, context):
    return {
        k: inject(v, context)
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


async def call_api(operation_config, context):

    details = operation_config["details"]

    method = details["method"]
    url = inject(details["route"], context)

    headers = build_headers(details, context)
    data = build_data(details, context)
    params = build_query_params(details, context)

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

            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error("HTTP error: %s - %s", e.response.status_code, e.response.text)
        raise

    except Exception as e:
        logger.exception("API call failed")
        raise