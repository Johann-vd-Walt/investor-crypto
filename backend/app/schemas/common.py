"""Shared schema helpers.

``DecimalAsFloat``: a field that stays a ``Decimal`` in Python (so all
arithmetic and DB round-trips remain exact — Guardrail 2.2) but serialises to a
JSON **number** rather than Pydantic v2's default Decimal-as-string. This keeps
the API payload numeric for the JS client while never introducing float into
computation. Only the presentation boundary is float.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

DecimalAsFloat = Annotated[
    Decimal,
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]
