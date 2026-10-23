"""The app must keep honouring contracts/openapi.json (what the mobile apps are built from). Additive differences are allowed."""
import json

import pytest

from app.config import REPO_ROOT
from app.main import create_app

CONTRACT = json.loads((REPO_ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def current():
    return create_app().openapi()


def operations(spec):
    return {(method, path): op for path, item in spec["paths"].items() for method, op in item.items() if method in HTTP_METHODS}


def schema_name(schema):
    if not schema:
        return None
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        return f"list[{schema_name(schema.get('items'))}]"
    return schema.get("type")


def response_schemas(op):
    return {status: schema_name(r.get("content", {}).get("application/json", {}).get("schema")) for status, r in op["responses"].items()}


def request_schema(op):
    content = (op.get("requestBody") or {}).get("content", {})
    for kind in ("application/json", "multipart/form-data"):
        if kind in content:
            return schema_name(content[kind].get("schema"))
    return None


def test_the_contract_is_not_empty():
    assert len(operations(CONTRACT)) >= 28


def test_every_contract_path_and_method_exists(current):
    missing = sorted(set(operations(CONTRACT)) - set(operations(current)))
    assert missing == [], f"endpoints removed from the app: {missing}"


def test_every_contract_response_keeps_its_model_name(current):
    app_ops = operations(current)
    problems = []
    for key, op in operations(CONTRACT).items():
        wanted, actual = response_schemas(op), response_schemas(app_ops[key])
        for status, name in wanted.items():
            if actual.get(status, "<missing>") != name:
                problems.append(f"{key} {status}: contract {name!r}, app {actual.get(status, '<missing>')!r}")
    assert problems == []


def test_every_contract_request_body_keeps_its_model_name(current):
    app_ops = operations(current)
    problems = [f"{key}: contract {request_schema(op)!r}, app {request_schema(app_ops[key])!r}"
                for key, op in operations(CONTRACT).items() if request_schema(op) != request_schema(app_ops[key])]
    assert problems == []


def test_every_contract_parameter_is_still_accepted(current):
    app_ops = operations(current)
    problems = []
    for key, op in operations(CONTRACT).items():
        have = {(p["in"], p["name"]) for p in app_ops[key].get("parameters", [])}
        problems += [f"{key}: {p}" for p in {(p["in"], p["name"]) for p in op.get("parameters", [])} - have]
    assert problems == []


def test_every_contract_model_keeps_its_fields_and_required_flags(current):
    contract, now = CONTRACT["components"]["schemas"], current["components"]["schemas"]
    problems = []
    for name, schema in contract.items():
        if name not in now:
            problems.append(f"model removed: {name}")
            continue
        for field, definition in schema.get("properties", {}).items():
            if field not in now[name].get("properties", {}):
                problems.append(f"{name}.{field} removed")
            elif definition.get("type") != now[name]["properties"][field].get("type"):
                problems.append(f"{name}.{field} changed type")
        newly_required = set(now[name].get("required", [])) - set(schema.get("required", []))
        if newly_required:
            problems.append(f"{name}: newly required {sorted(newly_required)}")
    assert problems == []


def test_authenticated_routes_are_marked_secured(current):
    ops = operations(current)
    assert ops[("get", "/v1/me")].get("security")
    assert not ops[("get", "/v1/meta")].get("security")
    assert not ops[("post", "/v1/auth/otp/request")].get("security")


def test_no_endpoint_is_left_unimplemented(api_client, auth):
    """Walk every documented non-admin route once: none may answer 501."""
    for (method, path), _op in operations(CONTRACT).items():
        if path.startswith("/admin") or "{" in path:
            continue
        response = api_client.request(method.upper(), path, headers=auth)
        assert response.status_code != 501, (method, path)
