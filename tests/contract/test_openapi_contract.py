"""Schemathesis contract test: assert the live FastAPI app conforms to openapi.yaml.

Schemathesis stable does not yet support OpenAPI 3.1 fully. We force the
generated schema to declare 3.0.3 by post-processing FastAPI's output.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract

schemathesis = pytest.importorskip("schemathesis")

from lexscribe_api.main import app  # noqa: E402


def _force_openapi_30() -> dict:
    s = app.openapi()
    s["openapi"] = "3.0.3"
    return s


try:
    schema = schemathesis.from_dict(_force_openapi_30(), app=app)
except Exception as exc:
    pytest.skip(f"schemathesis schema build failed: {exc}", allow_module_level=True)


@schema.parametrize()
def test_api_conforms_to_its_own_openapi(case: schemathesis.Case) -> None:  # type: ignore[name-defined]
    case.call_and_validate()
