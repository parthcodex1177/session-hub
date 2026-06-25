"""Model pricing table and cost estimation helper.

Prices are per million tokens (USD).
Rows: (model_substr, input_price_per_M, output_price_per_M)
First match wins — list more-specific substrings before less-specific ones.
"""
from __future__ import annotations

PRICING: list[tuple[str, float, float]] = [
    ("opus",              15.0,   75.0),
    ("sonnet",             3.0,   15.0),
    ("haiku",              0.80,   4.0),
    ("gemini-2.5-pro",     1.25,  10.0),
    ("gemini-2.5-flash",   0.15,   0.60),
    ("gemini-3-flash",     0.15,   0.60),
    ("gemini-2.0-flash",   0.10,   0.40),
    ("gemini-flash",       0.15,   0.60),
    ("gemini-pro",         1.25,  10.0),
]


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    models: list[str],
) -> float | None:
    """Return estimated USD cost for a session, or None if no model matched."""
    for model in models:
        m = model.lower()
        for match, inp_price, out_price in PRICING:
            if match in m:
                return (
                    input_tokens / 1_000_000 * inp_price
                    + output_tokens / 1_000_000 * out_price
                )
    return None
