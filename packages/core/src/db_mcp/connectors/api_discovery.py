"""API endpoint autodiscovery — OpenAPI spec parsing + response probing.

Given a base_url and auth config, discovers API endpoints, pagination strategy,
and response schema. Three-stage pipeline:

1. Try to find an OpenAPI/Swagger spec at well-known paths
2a. If found: parse spec → extract GET collection endpoints + fields
2b. If not found: probe base_url and common REST paths → infer endpoints
3. For each endpoint: infer column types + detect pagination pattern
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DiscoveredField:
    """A field (column) discovered from an API response or spec."""

    name: str
    type: str = "VARCHAR"  # VARCHAR, INTEGER, DOUBLE, BOOLEAN
    description: str = ""


@dataclass
class DiscoveredQueryParam:
    """A query parameter discovered from an API spec."""

    name: str
    type: str = "string"  # string, integer, number, boolean
    description: str = ""
    required: bool = False
    enum: list[str] | None = None
    default: str | None = None


@dataclass
class DiscoveredEndpoint:
    """An API endpoint discovered from a spec or probing."""

    name: str  # table name (e.g., "markets")
    path: str  # API path (e.g., "/markets")
    method: str = "GET"
    fields: list[DiscoveredField] = field(default_factory=list)
    query_params: list[DiscoveredQueryParam] = field(default_factory=list)


@dataclass
class DiscoveredPagination:
    """Pagination strategy discovered from spec or response analysis."""

    type: str = "none"  # cursor | offset | link_header | none
    cursor_param: str = ""
    cursor_field: str = ""
    offset_param: str = "offset"
    page_size_param: str = "limit"
    page_size: int = 100
    data_field: str = ""  # e.g., "data" if results wrapped


@dataclass
class DiscoveryResult:
    """Complete result of API discovery."""

    endpoints: list[DiscoveredEndpoint]
    pagination: DiscoveredPagination
    spec_url: str | None = None
    base_url: str | None = None
    strategy: str = "none"  # "openapi" | "probe" | "none"
    api_title: str = ""
    api_description: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# OpenAPI type → SQL type mapping
# ---------------------------------------------------------------------------

_OPENAPI_TYPE_MAP = {
    "string": "VARCHAR",
    "integer": "INTEGER",
    "number": "DOUBLE",
    "boolean": "BOOLEAN",
    "object": "VARCHAR",  # JSON serialised
    "array": "VARCHAR",  # JSON serialised
}

# Well-known paths for OpenAPI/Swagger specs
SPEC_PATHS = [
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger.yaml",
    "/api/openapi.json",
    "/api/swagger.json",
    "/api/docs/openapi.json",
    "/api/docs/openapi.yaml",
    "/api/docs/swagger.json",
    "/.well-known/openapi.json",
    "/v1/openapi.json",
    "/v2/api-docs",
    "/api-docs",
    "/docs/openapi.json",
    "/spec.json",
]

# Common REST collection paths to probe when no spec is found
_PROBE_PATHS = [
    "/markets",
    "/events",
    "/users",
    "/products",
    "/orders",
    "/items",
    "/assets",
    "/transactions",
    "/accounts",
    "/posts",
    "/data",
    "/api",
    "/v1",
    "/v2",
    "/api/v1",
    "/api/v2",
]

# Pagination-related cursor/next fields
_CURSOR_FIELDS = {
    "next_cursor",
    "next",
    "starting_after",
    "cursor",
    "next_token",
    "after",
    "nextPageToken",
}
_HAS_MORE_FIELDS = {"has_more", "hasMore", "has_next", "hasNext"}

# Path param patterns (detail endpoints to skip)
_PATH_PARAM_RE = re.compile(r"\{[^}]+\}")
_SPEC_URL_RE = re.compile(r"(?:^|/)(?:openapi|swagger|api-docs|spec)(?:\.(?:json|ya?ml))?$")


# ---------------------------------------------------------------------------
# Stage 1: OpenAPI/Swagger spec discovery
# ---------------------------------------------------------------------------


def discover_openapi_spec(
    base_url: str,
    auth_headers: dict[str, str],
    rate_limit_rps: float,
    spec_url: str | None = None,
) -> tuple[dict | None, str | None]:
    """Try well-known paths to find an OpenAPI/Swagger spec.

    Returns:
        (spec_dict, spec_url) or (None, None) if not found.
    """
    base = base_url.rstrip("/")
    delay = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0
    candidates: list[str] = []

    if spec_url:
        candidates.append(spec_url)
    elif is_probable_openapi_spec_url(base_url):
        candidates.append(base_url)

    candidates.extend(base + path for path in SPEC_PATHS)

    seen: set[str] = set()
    for url in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        spec = _fetch_spec_candidate(url, auth_headers, delay)
        if spec is not None:
            return spec, url

    return None, None


def is_probable_openapi_spec_url(url: str) -> bool:
    """Return True when a URL looks like a direct OpenAPI/Swagger document."""
    path = urlparse(url).path.rstrip("/").lower()
    return bool(_SPEC_URL_RE.search(path))


def _fetch_spec_candidate(
    url: str,
    auth_headers: dict[str, str],
    delay: float,
) -> dict[str, Any] | None:
    """Fetch and parse a candidate OpenAPI/Swagger document URL."""
    try:
        if delay > 0:
            time.sleep(delay)

        resp = requests.get(url, headers=auth_headers, timeout=10)
        if resp.status_code != 200:
            return None

        try:
            spec = resp.json()
        except (ValueError, TypeError):
            try:
                spec = yaml.safe_load(resp.text)
            except Exception:
                return None

        if not isinstance(spec, dict):
            return None

        if "openapi" in spec or "swagger" in spec:
            logger.info(f"Found OpenAPI spec at {url}")
            return spec
    except Exception:
        return None

    return None


# ---------------------------------------------------------------------------
# Stage 2a: OpenAPI spec parsing
# ---------------------------------------------------------------------------


def parse_openapi_spec(
    spec: dict,
) -> tuple[list[DiscoveredEndpoint], DiscoveredPagination, str, str]:
    """Parse an OpenAPI/Swagger spec to extract endpoints and fields.

    Returns:
        (endpoints, pagination, api_title, api_description)
    """
    info = spec.get("info", {})
    api_title = info.get("title", "")
    api_description = info.get("description", "")

    endpoints: list[DiscoveredEndpoint] = []
    all_pagination_params: list[str] = []

    is_swagger2 = "swagger" in spec
    paths = spec.get("paths", {})

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue

        # Skip likely detail endpoints whose final segment is a path param.
        # Keep collection endpoints that require contextual path params such as
        # /tenants/{tenant}/articles or /schools/{schoolAlias}/teams.
        if _is_likely_detail_endpoint(path):
            continue

        get_op = methods.get("get")
        if not get_op or not isinstance(get_op, dict):
            continue

        # Check if response returns an array (collection endpoint)
        response_schema = _get_response_schema(get_op, is_swagger2)
        if response_schema is None:
            # No schema — still include endpoint if it's a GET
            endpoint_name = _path_to_name(path)
            endpoints.append(DiscoveredEndpoint(name=endpoint_name, path=path))
            continue

        # Determine if this is a collection endpoint
        fields, is_wrapped, wrapper_field = _extract_fields_from_schema(response_schema, spec)

        # Extract query params
        discovered_params: list[DiscoveredQueryParam] = []
        params = get_op.get("parameters", [])
        for p in params:
            if not isinstance(p, dict):
                continue
            if p.get("in") == "query":
                pname = p.get("name", "")
                all_pagination_params.append(pname)
                schema = p.get("schema", {})
                # Swagger 2.0 puts type directly on the parameter
                if is_swagger2:
                    param_type = p.get("type", "string")
                else:
                    param_type = schema.get("type", "string")
                default_val = schema.get("default")
                discovered_params.append(
                    DiscoveredQueryParam(
                        name=pname,
                        type=param_type,
                        description=p.get("description", ""),
                        required=p.get("required", False),
                        enum=schema.get("enum"),
                        default=str(default_val) if default_val is not None else None,
                    )
                )

        endpoint_name = _path_to_name(path)
        endpoints.append(
            DiscoveredEndpoint(
                name=endpoint_name, path=path, fields=fields, query_params=discovered_params
            )
        )

    # Detect pagination from collected params and wrapped response pattern
    pagination = _detect_pagination_from_spec(all_pagination_params, spec)

    return endpoints, pagination, api_title, api_description


def _get_response_schema(operation: dict, is_swagger2: bool) -> dict | None:
    """Extract the response schema from a GET operation."""
    responses = operation.get("responses", {})
    success = responses.get("200", responses.get("201", {}))

    if is_swagger2:
        return success.get("schema")

    # OpenAPI 3.x
    content = success.get("content", {})
    json_content = content.get("application/json", {})
    return json_content.get("schema")


def _extract_fields_from_schema(
    schema: dict, full_spec: dict
) -> tuple[list[DiscoveredField], bool, str]:
    """Extract fields from a response schema, resolving $refs.

    Returns:
        (fields, is_wrapped, wrapper_field)
        is_wrapped: True if response is an object wrapping an array (e.g., {data: [...]})
        wrapper_field: The field name containing the array (e.g., "data")
    """
    schema = _resolve_ref(schema, full_spec)

    schema_type = schema.get("type", "")

    # Direct array response: {"type": "array", "items": {...}}
    if schema_type == "array":
        items = _resolve_ref(schema.get("items", {}), full_spec)
        return _extract_object_fields(items, full_spec), False, ""

    # Wrapped response: {"type": "object", "properties": {"data": {"type": "array", ...}}}
    if schema_type == "object":
        props = schema.get("properties", {})

        # Look for array fields that contain the data
        for key, prop_schema in props.items():
            prop_schema = _resolve_ref(prop_schema, full_spec)
            if prop_schema.get("type") == "array":
                items = _resolve_ref(prop_schema.get("items", {}), full_spec)
                return _extract_object_fields(items, full_spec), True, key

        # No array field found — extract top-level object fields
        return _extract_object_fields(schema, full_spec), False, ""

    return [], False, ""


def _extract_object_fields(schema: dict, full_spec: dict) -> list[DiscoveredField]:
    """Extract fields from an object schema."""
    schema = _resolve_ref(schema, full_spec)
    props = schema.get("properties", {})

    fields: list[DiscoveredField] = []
    for name, prop in props.items():
        prop = _resolve_ref(prop, full_spec)
        openapi_type = _normalize_openapi_type(prop.get("type", "string"))
        sql_type = _OPENAPI_TYPE_MAP.get(openapi_type, "VARCHAR")
        description = prop.get("description", "")
        fields.append(DiscoveredField(name=name, type=sql_type, description=description))

    return fields


def _normalize_openapi_type(openapi_type: Any) -> str:
    """Normalize OpenAPI type values to a single scalar type name."""
    if isinstance(openapi_type, list):
        for candidate in openapi_type:
            if isinstance(candidate, str) and candidate != "null":
                return candidate
        return "string"
    if isinstance(openapi_type, str):
        return openapi_type
    return "string"


def _resolve_ref(schema: dict, full_spec: dict) -> dict:
    """Resolve a $ref to the actual schema object."""
    if not isinstance(schema, dict):
        return schema

    ref = schema.get("$ref")
    if not ref:
        return schema

    # Handle local refs: #/components/schemas/Market or #/definitions/Market
    parts = ref.lstrip("#/").split("/")
    resolved = full_spec
    for part in parts:
        if isinstance(resolved, dict):
            resolved = resolved.get(part, {})
        else:
            return schema

    return resolved if isinstance(resolved, dict) else schema


def _path_to_name(path: str) -> str:
    """Convert an API path to a clean table name.

    /v1/markets → markets
    /events/active → events_active
    /api/v2/orders → orders
    """
    # Strip leading version prefixes
    cleaned = re.sub(r"^/(?:api/)?(?:v\d+/)?", "/", path)
    segments = [segment for segment in cleaned.strip("/").split("/") if segment]

    # Drop leading contextual prefixes that end with a path param:
    # /tenants/{tenant}/articles -> articles
    # /schools/{schoolAlias}/teams -> teams
    while len(segments) >= 3 and _PATH_PARAM_RE.fullmatch(segments[1]):
        segments = segments[2:]

    # Remove any remaining path-param segments from the table name.
    segments = [segment for segment in segments if not _PATH_PARAM_RE.fullmatch(segment)]

    name = "_".join(segments).replace("-", "_")
    return name or "root"


def _is_likely_detail_endpoint(path: str) -> bool:
    """Return True when the endpoint looks like a single-resource detail path."""
    segments = [segment for segment in path.strip("/").split("/") if segment]
    return bool(segments) and bool(_PATH_PARAM_RE.fullmatch(segments[-1]))


def _detect_pagination_from_spec(params: list[str], spec: dict) -> DiscoveredPagination:
    """Detect pagination strategy from collected query parameter names."""
    param_set = set(params)

    # Check for cursor-style params
    cursor_params = param_set & _CURSOR_FIELDS
    if cursor_params:
        cursor_param = next(iter(cursor_params))
        # Check if response wraps data (look at first GET endpoint)
        data_field = _detect_data_field_from_spec(spec)
        page_size_param = (
            "maxResults"
            if "maxResults" in param_set
            else "limit"
            if "limit" in param_set
            else ""
        )
        return DiscoveredPagination(
            type="cursor",
            cursor_param=cursor_param,
            cursor_field=cursor_param if cursor_param == "nextPageToken" else "data[-1].id",
            page_size_param=page_size_param,
            data_field=data_field,
        )

    # Check for offset-style params
    if "offset" in param_set or "startAt" in param_set:
        data_field = _detect_data_field_from_spec(spec)
        offset_param = "startAt" if "startAt" in param_set else "offset"
        page_size_param = (
            "maxResults" if "maxResults" in param_set else "limit" if "limit" in param_set else ""
        )
        return DiscoveredPagination(
            type="offset",
            offset_param=offset_param,
            page_size_param=page_size_param,
            data_field=data_field,
        )

    # Check for page-style params (treated as offset)
    if "page" in param_set:
        data_field = _detect_data_field_from_spec(spec)
        return DiscoveredPagination(
            type="offset",
            page_size_param=(
                "per_page"
                if "per_page" in param_set
                else "page_size"
                if "page_size" in param_set
                else "limit"
                if "limit" in param_set
                else ""
            ),
            data_field=data_field,
        )

    return DiscoveredPagination()


def _detect_data_field_from_spec(spec: dict) -> str:
    """Detect the data wrapping field from the first GET endpoint in the spec."""
    paths = spec.get("paths", {})
    is_swagger2 = "swagger" in spec

    for _path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        get_op = methods.get("get")
        if not get_op:
            continue

        response_schema = _get_response_schema(get_op, is_swagger2)
        if not response_schema:
            continue

        response_schema = _resolve_ref(response_schema, spec)
        if response_schema.get("type") == "object":
            props = response_schema.get("properties", {})
            for key, prop in props.items():
                prop = _resolve_ref(prop, spec)
                if prop.get("type") == "array":
                    return key

    return ""


def resolve_spec_base_url(spec: dict, spec_url: str | None, fallback_base_url: str) -> str:
    """Resolve the usable API base URL from spec metadata."""
    if "openapi" in spec:
        servers = spec.get("servers", [])
        if isinstance(servers, list):
            for server in servers:
                if not isinstance(server, dict):
                    continue
                server_url = str(server.get("url") or "").strip()
                if server_url:
                    return _resolve_server_url(server_url, spec_url, fallback_base_url)

    if "swagger" in spec:
        host = str(spec.get("host") or "").strip()
        if host:
            schemes = spec.get("schemes")
            scheme = ""
            if isinstance(schemes, list) and schemes:
                scheme = str(schemes[0]).strip()
            if not scheme:
                reference = spec_url or fallback_base_url
                scheme = urlparse(reference).scheme or "https"
            base_path = str(spec.get("basePath") or "").strip()
            return f"{scheme}://{host}{base_path}".rstrip("/")

    if spec_url and is_probable_openapi_spec_url(spec_url):
        return spec_url.rsplit("/", 1)[0]
    if is_probable_openapi_spec_url(fallback_base_url):
        return fallback_base_url.rsplit("/", 1)[0]
    return fallback_base_url.rstrip("/")


def _resolve_server_url(server_url: str, spec_url: str | None, fallback_base_url: str) -> str:
    """Resolve an OpenAPI server URL against the spec location or fallback base URL."""
    parsed = urlparse(server_url)
    if parsed.scheme and parsed.netloc:
        return server_url.rstrip("/")

    reference = spec_url or fallback_base_url
    if server_url.startswith("/"):
        ref = urlparse(reference)
        if ref.scheme and ref.netloc:
            return f"{ref.scheme}://{ref.netloc}{server_url}".rstrip("/")

    base_reference = reference
    if is_probable_openapi_spec_url(reference):
        base_reference = reference.rsplit("/", 1)[0] + "/"
    else:
        base_reference = reference.rstrip("/") + "/"
    return urljoin(base_reference, server_url).rstrip("/")


# ---------------------------------------------------------------------------
# Stage 2b: Response probing (fallback)
# ---------------------------------------------------------------------------


def probe_endpoints(
    base_url: str,
    auth_headers: dict[str, str],
    auth_params: dict[str, str],
    rate_limit_rps: float,
) -> tuple[list[DiscoveredEndpoint], DiscoveredPagination]:
    """Probe the API by hitting the base_url and common paths.

    Used as fallback when no OpenAPI spec is found.

    Returns:
        (endpoints, pagination)
    """
    base = base_url.rstrip("/")
    delay = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0
    endpoints: list[DiscoveredEndpoint] = []
    pagination = DiscoveredPagination()

    # First, try the base URL itself
    base_ep, base_pg = _probe_url(base, "/", auth_headers, auth_params, delay)
    if base_ep:
        endpoints.extend(base_ep)
        if base_pg and base_pg.type != "none":
            pagination = base_pg

    # Then try common REST paths
    for path in _PROBE_PATHS:
        url = base + path
        discovered, pg = _probe_url(url, path, auth_headers, auth_params, delay)
        if discovered:
            endpoints.extend(discovered)
            if pg and pg.type != "none" and pagination.type == "none":
                pagination = pg

    return endpoints, pagination


def _probe_url(
    url: str,
    path: str,
    auth_headers: dict[str, str],
    auth_params: dict[str, str],
    delay: float,
) -> tuple[list[DiscoveredEndpoint], DiscoveredPagination | None]:
    """Probe a single URL and analyze the response."""
    if delay > 0:
        time.sleep(delay)

    try:
        resp = requests.get(url, headers=auth_headers, params=auth_params, timeout=10)
        if resp.status_code != 200:
            return [], None

        content_type = resp.headers.get("content-type", "")
        if "json" not in content_type:
            return [], None

        body = resp.json()
        headers = dict(resp.headers)

    except Exception:
        return [], None

    endpoints: list[DiscoveredEndpoint] = []
    pg = detect_pagination(body, headers)

    if isinstance(body, list) and body:
        # Direct array response — this URL is a collection endpoint
        name = _path_to_name(path)
        fields = infer_schema_from_response(body)
        endpoints.append(DiscoveredEndpoint(name=name, path=path, fields=fields))

    elif isinstance(body, dict):
        # Object response — look for array values as sub-endpoints
        for key, value in body.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                fields = infer_schema_from_response(value)
                ep_path = path.rstrip("/") + "/" + key if path != "/" else "/" + key
                endpoints.append(DiscoveredEndpoint(name=key, path=ep_path, fields=fields))

    return endpoints, pg


# ---------------------------------------------------------------------------
# Stage 3: Schema inference from response data
# ---------------------------------------------------------------------------


def infer_schema_from_response(data: list[dict]) -> list[DiscoveredField]:
    """Infer column names and types from JSON response data.

    Handles:
    - Basic types: str→VARCHAR, int→INTEGER, float→DOUBLE, bool→BOOLEAN
    - Nested dicts: flattened with _ separator
    - Null values: default to VARCHAR
    - Multiple rows: union of all fields
    """
    if not data:
        return []

    # Collect all field→type pairs across all rows
    field_types: dict[str, str] = {}

    for row in data:
        if not isinstance(row, dict):
            continue
        _collect_fields(row, "", field_types)

    return [DiscoveredField(name=name, type=sql_type) for name, sql_type in field_types.items()]


def _collect_fields(obj: dict, prefix: str, field_types: dict[str, str]) -> None:
    """Recursively collect fields from a dict, flattening nested objects."""
    for key, value in obj.items():
        full_name = f"{prefix}{key}" if not prefix else f"{prefix}_{key}"

        if isinstance(value, dict):
            # Flatten nested objects
            _collect_fields(value, full_name, field_types)
        elif isinstance(value, list):
            # Arrays: note as VARCHAR (JSON serialised)
            if full_name not in field_types:
                field_types[full_name] = "VARCHAR"
        else:
            inferred = _infer_python_type(value)
            # Don't downgrade a more specific type
            existing = field_types.get(full_name)
            if existing is None or existing == "VARCHAR" and inferred != "VARCHAR":
                field_types[full_name] = inferred


def _infer_python_type(value: Any) -> str:
    """Map a Python value to a SQL type."""
    if value is None:
        return "VARCHAR"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "DOUBLE"
    return "VARCHAR"


# ---------------------------------------------------------------------------
# Stage 3: Pagination detection from response
# ---------------------------------------------------------------------------


def detect_pagination(
    response_body: Any,
    response_headers: dict[str, str],
) -> DiscoveredPagination:
    """Detect pagination strategy from a single API response.

    Checks:
    - Link header → link_header pagination
    - has_more / hasMore → cursor pagination
    - next_cursor / next / starting_after → cursor pagination
    - total + offset → offset pagination
    - data / results wrapping → sets data_field
    """
    # Check Link header first
    link_header = response_headers.get("Link", response_headers.get("link", ""))
    if link_header and 'rel="next"' in link_header:
        return DiscoveredPagination(type="link_header")

    if not isinstance(response_body, dict):
        return DiscoveredPagination()

    keys = set(response_body.keys())

    # Detect data wrapping field
    data_field = ""
    for candidate in ("data", "results", "items", "records", "entries", "issues", "values"):
        if candidate in keys and isinstance(response_body.get(candidate), list):
            data_field = candidate
            break

    # Check for cursor pagination signals
    if keys & _HAS_MORE_FIELDS:
        return DiscoveredPagination(type="cursor", data_field=data_field)

    if "isLast" in keys:
        cursor_param = "nextPageToken" if "nextPageToken" in keys else ""
        return DiscoveredPagination(
            type="cursor",
            cursor_param=cursor_param,
            cursor_field=cursor_param,
            data_field=data_field,
        )

    if keys & _CURSOR_FIELDS:
        cursor_key = next(iter(keys & _CURSOR_FIELDS))
        return DiscoveredPagination(
            type="cursor",
            cursor_param=cursor_key,
            cursor_field=cursor_key,
            data_field=data_field,
        )

    # Check for offset pagination signals
    if "total" in keys and ({"offset", "limit"} & keys or {"startAt", "maxResults"} & keys):
        offset_param = "startAt" if "startAt" in keys else "offset"
        page_size_param = (
            "maxResults" if "maxResults" in keys else "limit" if "limit" in keys else ""
        )
        return DiscoveredPagination(
            type="offset",
            data_field=data_field,
            offset_param=offset_param,
            page_size_param=page_size_param,
        )

    # If we found a wrapping field but no pagination signals
    if data_field:
        return DiscoveredPagination(data_field=data_field)

    return DiscoveredPagination()


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def discover_api(
    base_url: str,
    auth_headers: dict[str, str],
    auth_params: dict[str, str],
    rate_limit_rps: float,
    spec_url: str | None = None,
) -> DiscoveryResult:
    """Discover API endpoints, pagination, and schema.

    Three-stage pipeline:
    1. Try to find an OpenAPI/Swagger spec
    2a. Parse spec if found
    2b. Probe endpoints if no spec
    3. Infer schema from responses (during probe, or from spec)

    Args:
        base_url: API base URL
        auth_headers: Authentication headers
        auth_params: Authentication query params
        rate_limit_rps: Rate limit (requests per second)
        spec_url: Optional explicit OpenAPI document URL

    Returns:
        DiscoveryResult with discovered endpoints and config
    """
    errors: list[str] = []

    # Stage 1: Try OpenAPI spec discovery
    try:
        spec, discovered_spec_url = discover_openapi_spec(
            base_url,
            auth_headers,
            rate_limit_rps,
            spec_url=spec_url,
        )
    except Exception as exc:
        spec, discovered_spec_url = None, None
        errors.append(f"Spec discovery failed: {exc}")

    # Stage 2a: Parse spec if found
    if spec is not None:
        try:
            endpoints, pagination, title, description = parse_openapi_spec(spec)
            return DiscoveryResult(
                endpoints=endpoints,
                pagination=pagination,
                spec_url=discovered_spec_url,
                base_url=resolve_spec_base_url(spec, discovered_spec_url, base_url),
                strategy="openapi",
                api_title=title,
                api_description=description,
                errors=errors,
            )
        except Exception as exc:
            errors.append(f"Spec parsing failed: {exc}")

    # Stage 2b: Probe endpoints (fallback)
    try:
        endpoints, pagination = probe_endpoints(
            base_url, auth_headers, auth_params, rate_limit_rps
        )
        if endpoints:
            return DiscoveryResult(
                endpoints=endpoints,
                pagination=pagination,
                strategy="probe",
                errors=errors,
            )
    except Exception as exc:
        errors.append(f"Endpoint probing failed: {exc}")

    # Nothing found
    return DiscoveryResult(
        endpoints=[],
        pagination=DiscoveredPagination(),
        strategy="none",
        errors=errors or ["No endpoints discovered"],
    )
