import asyncio
from wize_jmes_adapter import Adapter


# -------------------------------
# Ticket Detail
# -------------------------------
async def get_ticket_detail(adapter, ticket_id: str):
    print("\n===== TICKET DETAIL =====\n")

    result = await adapter.run(
        "smax_ticket_summary",
        context={
            "auth_token": "your-token-here",
            "ticket_id": ticket_id
        }
    )

    for r in result:
        print(r)


# -------------------------------
# Ticket List
# -------------------------------
async def get_ticket_list(adapter):
    print("\n===== TICKET LIST =====\n")

    result = await adapter.run(
        "smax_ticket_list",
        context={"auth_token": "your-token-here"}
    )
    for r in result[:5]:
        print(r)


# -------------------------------
# Comments WITH ticket_id
# -------------------------------
async def get_ticket_comments(adapter, ticket_id: str):
    print("\n===== COMMENTS (FILTERED) =====\n")

    result = await adapter.run(
        "smax_ticket_comments",
        context={
            "auth_token": "your-token-here",
            "ticket_id": ticket_id
        }
    )

    for r in result:
        print(r)


# -------------------------------
# Comments WITHOUT ticket_id
# -------------------------------
async def get_all_comments(adapter):
    print("\n===== ALL COMMENTS (RAW STRUCTURE) =====\n")

    result = await adapter.run(
        "smax_all_comments",
        context={
            "auth_token": "your-token-here"
            # no ticket_id → selector fallback
        }
    )

    for r in result[:5]:
        print(r)


# -------------------------------
# Multi-step (Full Ticket View)
# -------------------------------
async def get_full_ticket(adapter, ticket_id: str):
    print("\n===== FULL TICKET (MULTI-STEP) =====\n")

    result = await adapter.run(
        "smax_ticket_full",
        context={
            "auth_token": "your-token-here",
            "ticket_id": ticket_id
        }
    )

    for r in result:
        print(r)


# -------------------------------
# Main
# -------------------------------
async def main():
    adapter = Adapter("config.yaml")

    ticket_id = "14592"

    await get_ticket_detail(adapter, ticket_id)
    await get_ticket_list(adapter)
    await get_ticket_comments(adapter, ticket_id)
    await get_all_comments(adapter)          # 🔥 NEW
    await get_full_ticket(adapter, ticket_id)  # 🔥 NEW


if __name__ == "__main__":
    asyncio.run(main())