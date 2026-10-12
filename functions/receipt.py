"""Serverless function: tamper-evident booking receipt (Unit 4: Serverless Architectures)."""

import hashlib


def handler(event: dict, context) -> dict:
    reservation_id = str(event.get("reservation_id", ""))
    slot_id = str(event.get("slot_id", ""))
    price = float(event.get("price_per_hour", 0))
    block = event.get("ledger_block", -1)

    body = f"{reservation_id}|{slot_id}|{price:.2f}|{block}"
    return {
        "receipt_no": "RCPT-" + hashlib.sha256(body.encode()).hexdigest()[:10].upper(),
        "reservation_id": reservation_id,
        "slot_id": slot_id,
        "price_per_hour": price,
        "ledger_block": block,
        "request_id": getattr(context, "request_id", None),
    }
