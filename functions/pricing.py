"""Serverless function: dynamic parking price (Unit 4: Serverless Architectures).

Written in the AWS-Lambda shape - a stateless `handler(event, context)` that
takes JSON in and returns JSON out, holds no state between calls and knows
nothing about how it is hosted. services/faas/runtime.py plays the role of the
FaaS platform (cold start, scale-to-zero, per-invocation billing); the same
handler could be zipped and deployed to AWS Lambda unchanged.
"""

BASE_PRICE_PER_HOUR = 20.0   # INR
PEAK_HOURS = {8, 9, 10, 16, 17, 18}


def handler(event: dict, context) -> dict:
    occupancy = max(0.0, min(1.0, float(event.get("occupancy", 0.0))))
    hour = int(event.get("hour", 12))

    if occupancy < 0.5:
        surge = 1.0
    elif occupancy < 0.8:
        surge = 1.25
    else:
        surge = 1.5
    peak = 1.1 if hour in PEAK_HOURS else 1.0

    return {
        "zone": event.get("zone"),
        "price_per_hour": round(BASE_PRICE_PER_HOUR * surge * peak, 2),
        "currency": "INR",
        "surge_multiplier": surge,
        "peak_multiplier": peak,
        "occupancy": occupancy,
    }
