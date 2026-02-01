"""TDD tests for API endpoint autodiscovery — written before implementation."""

from unittest.mock import MagicMock, patch

from db_mcp.connectors.api_discovery import (
    DiscoveredPagination,
    DiscoveryResult,
    detect_pagination,
    discover_api,
    discover_openapi_spec,
    infer_schema_from_response,
    parse_openapi_spec,
    probe_endpoints,
)

# ---------------------------------------------------------------------------
# Fixtures — OpenAPI specs
# ---------------------------------------------------------------------------

OPENAPI_3_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "description": "A test API", "version": "1.0.0"},
    "paths": {
        "/markets": {
            "get": {
                "summary": "List markets",
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                    {"name": "offset", "in": "query", "schema": {"type": "integer"}},
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Market"},
                                }
                            }
                        }
                    }
                },
            }
        },
        "/markets/{id}": {
            "get": {
                "summary": "Get market by ID",
                "parameters": [
                    {"name": "id", "in": "path", "required": True},
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Market"}}
                        }
                    }
                },
            }
        },
        "/events": {
            "get": {
                "summary": "List events",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Event"},
                                }
                            }
                        }
                    }
                },
            }
        },
        "/events/{slug}": {
            "get": {
                "summary": "Get event by slug",
                "responses": {"200": {}},
            }
        },
        "/admin/stats": {
            "post": {
                "summary": "Admin stats",
                "responses": {"200": {}},
            }
        },
    },
    "components": {
        "schemas": {
            "Market": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Market ID"},
                    "question": {"type": "string", "description": "Market question"},
                    "volume": {"type": "number", "description": "Trading volume"},
                    "active": {"type": "boolean"},
                },
            },
            "Event": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "start_date": {"type": "string", "format": "date-time"},
                },
            },
        }
    },
}


SWAGGER_2_SPEC = {
    "swagger": "2.0",
    "info": {"title": "Legacy API", "version": "1.0"},
    "basePath": "/v1",
    "paths": {
        "/users": {
            "get": {
                "summary": "List users",
                "parameters": [
                    {"name": "limit", "in": "query", "type": "integer"},
                ],
                "responses": {
                    "200": {
                        "schema": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer"},
                                    "name": {"type": "string"},
                                    "email": {"type": "string"},
                                },
                            },
                        }
                    }
                },
            }
        },
    },
}


OPENAPI_WRAPPED_RESPONSE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Wrapped API", "version": "1.0"},
    "paths": {
        "/charges": {
            "get": {
                "summary": "List charges",
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                    {
                        "name": "starting_after",
                        "in": "query",
                        "schema": {"type": "string"},
                    },
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "data": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "string"},
                                                    "amount": {"type": "integer"},
                                                },
                                            },
                                        },
                                        "has_more": {"type": "boolean"},
                                    },
                                }
                            }
                        }
                    }
                },
            }
        }
    },
}


# ---------------------------------------------------------------------------
# Spec discovery
# ---------------------------------------------------------------------------


class TestDiscoverOpenAPISpec:
    """Stage 1: finding an OpenAPI/Swagger spec at well-known paths."""

    def test_finds_spec_at_openapi_json(self):
        """Should find spec at /openapi.json."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = OPENAPI_3_SPEC

        not_found = MagicMock()
        not_found.status_code = 404

        def mock_get(url, **kwargs):
            if url.endswith("/openapi.json"):
                return mock_resp
            return not_found

        with patch("db_mcp.connectors.api_discovery.requests.get", side_effect=mock_get):
            spec, spec_url = discover_openapi_spec("https://api.example.com", {}, 10.0)

        assert spec is not None
        assert spec["openapi"] == "3.0.0"
        assert spec_url == "https://api.example.com/openapi.json"

    def test_finds_swagger_spec(self):
        """Should find Swagger 2.0 spec at /swagger.json."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = SWAGGER_2_SPEC

        not_found = MagicMock()
        not_found.status_code = 404

        def mock_get(url, **kwargs):
            if url.endswith("/swagger.json"):
                return mock_resp
            return not_found

        with patch("db_mcp.connectors.api_discovery.requests.get", side_effect=mock_get):
            spec, spec_url = discover_openapi_spec("https://api.example.com", {}, 10.0)

        assert spec is not None
        assert spec["swagger"] == "2.0"

    def test_returns_none_when_no_spec(self):
        """Should return None if no spec found at any path."""
        not_found = MagicMock()
        not_found.status_code = 404

        with patch("db_mcp.connectors.api_discovery.requests.get", return_value=not_found):
            spec, spec_url = discover_openapi_spec("https://api.example.com", {}, 10.0)

        assert spec is None
        assert spec_url is None

    def test_handles_timeout(self):
        """Should handle timeout gracefully."""
        with patch(
            "db_mcp.connectors.api_discovery.requests.get",
            side_effect=Exception("Timeout"),
        ):
            spec, spec_url = discover_openapi_spec("https://api.example.com", {}, 10.0)

        assert spec is None

    def test_passes_auth_headers(self):
        """Should pass auth headers when probing for spec."""
        not_found = MagicMock()
        not_found.status_code = 404

        with patch(
            "db_mcp.connectors.api_discovery.requests.get", return_value=not_found
        ) as mock_get:
            discover_openapi_spec(
                "https://api.example.com",
                {"Authorization": "Bearer test"},
                10.0,
            )

        # Verify auth headers were passed
        for call in mock_get.call_args_list:
            assert call.kwargs.get("headers", {}).get("Authorization") == "Bearer test"

    def test_handles_yaml_spec(self):
        """Should handle YAML-formatted specs."""
        import yaml

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/yaml"}
        mock_resp.json.side_effect = ValueError("Not JSON")
        mock_resp.text = yaml.dump(OPENAPI_3_SPEC)

        not_found = MagicMock()
        not_found.status_code = 404

        def mock_get(url, **kwargs):
            if url.endswith("/openapi.yaml"):
                return mock_resp
            return not_found

        with patch("db_mcp.connectors.api_discovery.requests.get", side_effect=mock_get):
            spec, spec_url = discover_openapi_spec("https://api.example.com", {}, 10.0)

        assert spec is not None
        assert spec["openapi"] == "3.0.0"


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


class TestParseOpenAPISpec:
    """Stage 2a: parsing OpenAPI specs to extract endpoints and fields."""

    def test_extracts_get_collection_endpoints(self):
        """Should extract GET endpoints that return arrays."""
        endpoints, pagination, title, description = parse_openapi_spec(OPENAPI_3_SPEC)
        names = {ep.name for ep in endpoints}
        assert "markets" in names
        assert "events" in names

    def test_skips_detail_endpoints(self):
        """Should skip endpoints with path params like {id} or {slug}."""
        endpoints, _, _, _ = parse_openapi_spec(OPENAPI_3_SPEC)
        paths = {ep.path for ep in endpoints}
        assert "/markets/{id}" not in paths
        assert "/events/{slug}" not in paths

    def test_skips_non_get_methods(self):
        """Should skip POST/PUT/DELETE endpoints."""
        endpoints, _, _, _ = parse_openapi_spec(OPENAPI_3_SPEC)
        names = {ep.name for ep in endpoints}
        assert "admin_stats" not in names

    def test_extracts_response_fields(self):
        """Should extract field names and types from response schema."""
        endpoints, _, _, _ = parse_openapi_spec(OPENAPI_3_SPEC)
        markets = next(ep for ep in endpoints if ep.name == "markets")
        field_names = {f.name for f in markets.fields}
        assert "id" in field_names
        assert "question" in field_names
        assert "volume" in field_names
        assert "active" in field_names

    def test_maps_openapi_types(self):
        """Should map OpenAPI types to SQL types."""
        endpoints, _, _, _ = parse_openapi_spec(OPENAPI_3_SPEC)
        markets = next(ep for ep in endpoints if ep.name == "markets")
        field_types = {f.name: f.type for f in markets.fields}
        assert field_types["id"] == "VARCHAR"
        assert field_types["volume"] == "DOUBLE"
        assert field_types["active"] == "BOOLEAN"

    def test_extracts_field_descriptions(self):
        """Should extract field descriptions from spec."""
        endpoints, _, _, _ = parse_openapi_spec(OPENAPI_3_SPEC)
        markets = next(ep for ep in endpoints if ep.name == "markets")
        id_field = next(f for f in markets.fields if f.name == "id")
        assert id_field.description == "Market ID"

    def test_extracts_api_info(self):
        """Should extract title and description from spec info."""
        _, _, title, description = parse_openapi_spec(OPENAPI_3_SPEC)
        assert title == "Test API"
        assert description == "A test API"

    def test_detects_pagination_params(self):
        """Should detect pagination parameters from query params."""
        endpoints, pagination, _, _ = parse_openapi_spec(OPENAPI_3_SPEC)
        # /markets has limit and offset params
        assert pagination.type in ("offset", "cursor", "none")

    def test_swagger_2_parsing(self):
        """Should parse Swagger 2.0 specs."""
        endpoints, _, title, _ = parse_openapi_spec(SWAGGER_2_SPEC)
        assert title == "Legacy API"
        names = {ep.name for ep in endpoints}
        assert "users" in names

    def test_swagger_2_extracts_fields(self):
        """Should extract inline schema fields from Swagger 2.0."""
        endpoints, _, _, _ = parse_openapi_spec(SWAGGER_2_SPEC)
        users = next(ep for ep in endpoints if ep.name == "users")
        field_names = {f.name for f in users.fields}
        assert "id" in field_names
        assert "name" in field_names
        assert "email" in field_names

    def test_resolves_ref(self):
        """Should resolve $ref references to components/schemas."""
        endpoints, _, _, _ = parse_openapi_spec(OPENAPI_3_SPEC)
        markets = next(ep for ep in endpoints if ep.name == "markets")
        assert len(markets.fields) == 4  # id, question, volume, active

    def test_wrapped_response_detects_data_field(self):
        """Should detect wrapped responses (e.g., {data: [...], has_more: true})."""
        endpoints, pagination, _, _ = parse_openapi_spec(OPENAPI_WRAPPED_RESPONSE_SPEC)
        assert pagination.data_field == "data"

    def test_wrapped_response_detects_cursor_pagination(self):
        """Should detect cursor pagination from starting_after param + has_more."""
        endpoints, pagination, _, _ = parse_openapi_spec(OPENAPI_WRAPPED_RESPONSE_SPEC)
        assert pagination.type == "cursor"
        assert pagination.cursor_param == "starting_after"

    def test_endpoint_name_from_path(self):
        """Should derive clean table names from paths."""
        endpoints, _, _, _ = parse_openapi_spec(OPENAPI_3_SPEC)
        names = {ep.name for ep in endpoints}
        # /markets → markets, /events → events
        assert "markets" in names
        assert "events" in names

    def test_empty_spec_returns_empty(self):
        """Should handle spec with no paths gracefully."""
        spec = {"openapi": "3.0.0", "info": {"title": "Empty"}, "paths": {}}
        endpoints, _, title, _ = parse_openapi_spec(spec)
        assert endpoints == []
        assert title == "Empty"

    def test_extracts_query_params(self):
        """Should populate query_params on DiscoveredEndpoint from spec parameters."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Params API"},
            "paths": {
                "/events": {
                    "get": {
                        "parameters": [
                            {
                                "name": "active",
                                "in": "query",
                                "schema": {"type": "boolean"},
                                "description": "Filter by active status",
                            },
                            {
                                "name": "order",
                                "in": "query",
                                "schema": {
                                    "type": "string",
                                    "enum": ["startDate", "endDate", "volume"],
                                },
                                "description": "Sort field",
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "schema": {"type": "integer", "default": 100},
                            },
                        ],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {"id": {"type": "string"}},
                                            },
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            },
        }
        endpoints, _, _, _ = parse_openapi_spec(spec)
        events = next(ep for ep in endpoints if ep.name == "events")
        assert len(events.query_params) == 3
        names = {qp.name for qp in events.query_params}
        assert "active" in names
        assert "order" in names
        assert "limit" in names

    def test_query_param_metadata(self):
        """Should capture type, description, required, enum, default on query params."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Meta API"},
            "paths": {
                "/items": {
                    "get": {
                        "parameters": [
                            {
                                "name": "status",
                                "in": "query",
                                "required": True,
                                "schema": {
                                    "type": "string",
                                    "enum": ["open", "closed"],
                                    "default": "open",
                                },
                                "description": "Filter by status",
                            },
                        ],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "array", "items": {"type": "object"}}
                                    }
                                }
                            }
                        },
                    }
                }
            },
        }
        endpoints, _, _, _ = parse_openapi_spec(spec)
        items = next(ep for ep in endpoints if ep.name == "items")
        status_param = next(qp for qp in items.query_params if qp.name == "status")
        assert status_param.type == "string"
        assert status_param.description == "Filter by status"
        assert status_param.required is True
        assert status_param.enum == ["open", "closed"]
        assert status_param.default == "open"

    def test_excludes_path_params_from_query_params(self):
        """Path params like {id} should not appear in query_params."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Path API"},
            "paths": {
                "/items": {
                    "get": {
                        "parameters": [
                            {"name": "page", "in": "query", "schema": {"type": "integer"}},
                            {
                                "name": "id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "array", "items": {"type": "object"}}
                                    }
                                }
                            }
                        },
                    }
                }
            },
        }
        endpoints, _, _, _ = parse_openapi_spec(spec)
        items = next(ep for ep in endpoints if ep.name == "items")
        names = {qp.name for qp in items.query_params}
        assert "page" in names
        assert "id" not in names


# ---------------------------------------------------------------------------
# Response probing (fallback)
# ---------------------------------------------------------------------------


class TestProbeEndpoints:
    """Stage 2b: probing base_url when no OpenAPI spec is found."""

    def test_discovers_from_json_array_response(self):
        """If base_url returns a JSON array, treat root as an endpoint."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = [
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"},
        ]

        with patch("db_mcp.connectors.api_discovery.requests.get", return_value=mock_resp):
            endpoints, pagination = probe_endpoints("https://api.example.com/items", {}, {}, 10.0)

        assert len(endpoints) >= 1
        # Root response is an array — should have fields inferred
        root_ep = endpoints[0]
        field_names = {f.name for f in root_ep.fields}
        assert "id" in field_names
        assert "name" in field_names

    def test_discovers_from_object_with_array_values(self):
        """If base_url returns an object with array values, each array key is an endpoint."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {
            "markets": [{"id": 1}, {"id": 2}],
            "events": [{"id": 10}],
            "total": 100,  # non-array, should be ignored
        }

        with patch("db_mcp.connectors.api_discovery.requests.get", return_value=mock_resp):
            endpoints, _ = probe_endpoints("https://api.example.com", {}, {}, 10.0)

        names = {ep.name for ep in endpoints}
        assert "markets" in names
        assert "events" in names

    def test_probes_common_paths(self):
        """Should try common REST paths when base_url is not directly useful."""
        call_count = {"n": 0}

        def mock_get(url, **kwargs):
            call_count["n"] += 1
            resp = MagicMock()
            if "/markets" in url:
                resp.status_code = 200
                resp.headers = {"content-type": "application/json"}
                resp.json.return_value = [{"id": 1, "question": "Will X happen?"}]
            else:
                resp.status_code = 404
                resp.headers = {"content-type": "text/html"}
                resp.json.side_effect = ValueError("Not JSON")
            return resp

        with patch("db_mcp.connectors.api_discovery.requests.get", side_effect=mock_get):
            endpoints, _ = probe_endpoints("https://api.example.com", {}, {}, 10.0)

        names = {ep.name for ep in endpoints}
        assert "markets" in names

    def test_handles_non_json_response(self):
        """Should handle HTML or error responses gracefully."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.json.side_effect = ValueError("Not JSON")

        not_found = MagicMock()
        not_found.status_code = 404
        not_found.headers = {"content-type": "text/html"}
        not_found.json.side_effect = ValueError("Not JSON")

        with patch("db_mcp.connectors.api_discovery.requests.get", return_value=not_found):
            endpoints, _ = probe_endpoints("https://api.example.com", {}, {}, 10.0)

        # Should not crash, may return empty
        assert isinstance(endpoints, list)

    def test_passes_auth(self):
        """Should pass auth headers and params when probing."""
        not_found = MagicMock()
        not_found.status_code = 404
        not_found.headers = {"content-type": "text/html"}
        not_found.json.side_effect = ValueError("Not JSON")

        with patch(
            "db_mcp.connectors.api_discovery.requests.get", return_value=not_found
        ) as mock_get:
            probe_endpoints(
                "https://api.example.com",
                {"Authorization": "Bearer test"},
                {"api_key": "123"},
                10.0,
            )

        for call in mock_get.call_args_list:
            assert call.kwargs.get("headers", {}).get("Authorization") == "Bearer test"
            assert call.kwargs.get("params", {}).get("api_key") == "123"


# ---------------------------------------------------------------------------
# Schema inference
# ---------------------------------------------------------------------------


class TestInferSchemaFromResponse:
    """Stage 3: infer column types from JSON response data."""

    def test_infers_string_type(self):
        fields = infer_schema_from_response([{"name": "Alice"}])
        assert fields[0].name == "name"
        assert fields[0].type == "VARCHAR"

    def test_infers_integer_type(self):
        fields = infer_schema_from_response([{"count": 42}])
        f = next(f for f in fields if f.name == "count")
        assert f.type == "INTEGER"

    def test_infers_float_type(self):
        fields = infer_schema_from_response([{"price": 19.99}])
        f = next(f for f in fields if f.name == "price")
        assert f.type == "DOUBLE"

    def test_infers_boolean_type(self):
        fields = infer_schema_from_response([{"active": True}])
        f = next(f for f in fields if f.name == "active")
        assert f.type == "BOOLEAN"

    def test_null_defaults_to_varchar(self):
        fields = infer_schema_from_response([{"unknown": None}])
        f = next(f for f in fields if f.name == "unknown")
        assert f.type == "VARCHAR"

    def test_flattens_nested_objects(self):
        """Nested dicts should be flattened with _ separator."""
        fields = infer_schema_from_response([{"address": {"city": "NYC", "zip": "10001"}}])
        field_names = {f.name for f in fields}
        assert "address_city" in field_names
        assert "address_zip" in field_names

    def test_multiple_rows_union_fields(self):
        """Should union fields across multiple rows."""
        fields = infer_schema_from_response(
            [
                {"id": 1, "name": "Alice"},
                {"id": 2, "email": "bob@test.com"},
            ]
        )
        field_names = {f.name for f in fields}
        assert "id" in field_names
        assert "name" in field_names
        assert "email" in field_names

    def test_empty_data_returns_empty(self):
        fields = infer_schema_from_response([])
        assert fields == []

    def test_integer_vs_float_distinction(self):
        """Should distinguish int (42) from float (42.0)."""
        fields = infer_schema_from_response([{"int_val": 42, "float_val": 42.0}])
        type_map = {f.name: f.type for f in fields}
        assert type_map["int_val"] == "INTEGER"
        assert type_map["float_val"] == "DOUBLE"


# ---------------------------------------------------------------------------
# Pagination detection
# ---------------------------------------------------------------------------


class TestDetectPagination:
    """Stage 3: detect pagination from response body and headers."""

    def test_detects_cursor_from_has_more(self):
        body = {"data": [{"id": "abc"}], "has_more": True}
        pg = detect_pagination(body, {})
        assert pg.type == "cursor"
        assert pg.data_field == "data"

    def test_detects_cursor_from_next_cursor(self):
        body = {"results": [{"id": 1}], "next_cursor": "abc123"}
        pg = detect_pagination(body, {})
        assert pg.type == "cursor"

    def test_detects_link_header_pagination(self):
        headers = {"Link": '<https://api.example.com/items?page=2>; rel="next"'}
        body = [{"id": 1}]
        pg = detect_pagination(body, headers)
        assert pg.type == "link_header"

    def test_detects_offset_pagination(self):
        body = {"results": [{"id": 1}], "total": 100, "offset": 0, "limit": 10}
        pg = detect_pagination(body, {})
        assert pg.type == "offset"

    def test_detects_no_pagination(self):
        body = [{"id": 1}, {"id": 2}]
        pg = detect_pagination(body, {})
        assert pg.type == "none"

    def test_detects_data_field_wrapping(self):
        body = {"data": [{"id": 1}], "meta": {"page": 1}}
        pg = detect_pagination(body, {})
        assert pg.data_field == "data"

    def test_detects_results_field_wrapping(self):
        body = {"results": [{"id": 1}], "total": 50}
        pg = detect_pagination(body, {})
        assert pg.data_field == "results"


# ---------------------------------------------------------------------------
# Full discovery orchestration
# ---------------------------------------------------------------------------


class TestDiscoverAPI:
    """End-to-end discover_api orchestration."""

    def test_uses_openapi_when_spec_found(self):
        """Should use OpenAPI strategy when spec is available."""
        spec_resp = MagicMock()
        spec_resp.status_code = 200
        spec_resp.headers = {"content-type": "application/json"}
        spec_resp.json.return_value = OPENAPI_3_SPEC

        not_found = MagicMock()
        not_found.status_code = 404

        def mock_get(url, **kwargs):
            if url.endswith("/openapi.json"):
                return spec_resp
            return not_found

        with patch("db_mcp.connectors.api_discovery.requests.get", side_effect=mock_get):
            result = discover_api("https://api.example.com", {}, {}, 10.0)

        assert result.strategy == "openapi"
        assert result.spec_url is not None
        assert len(result.endpoints) >= 2
        assert result.api_title == "Test API"

    def test_falls_back_to_probe(self):
        """Should fall back to probing when no spec found."""
        probe_resp = MagicMock()
        probe_resp.status_code = 200
        probe_resp.headers = {"content-type": "application/json"}
        probe_resp.json.return_value = [
            {"id": 1, "name": "Market A"},
        ]

        not_found = MagicMock()
        not_found.status_code = 404
        not_found.headers = {"content-type": "text/html"}
        not_found.json.side_effect = ValueError("Not JSON")

        call_count = {"n": 0}

        def mock_get(url, **kwargs):
            call_count["n"] += 1
            # All spec paths return 404
            for spec_path in [
                "/openapi.json",
                "/openapi.yaml",
                "/swagger.json",
                "/swagger.yaml",
                "/api/openapi.json",
                "/api/swagger.json",
                "/.well-known/openapi.json",
                "/v1/openapi.json",
                "/v2/api-docs",
                "/api-docs",
                "/docs/openapi.json",
                "/spec.json",
            ]:
                if url.endswith(spec_path):
                    return not_found

            # Base URL returns array
            if url.rstrip("/") == "https://api.example.com":
                return probe_resp
            return not_found

        with patch("db_mcp.connectors.api_discovery.requests.get", side_effect=mock_get):
            result = discover_api("https://api.example.com", {}, {}, 10.0)

        assert result.strategy == "probe"
        assert len(result.endpoints) >= 1

    def test_returns_empty_on_total_failure(self):
        """Should return empty result with errors if nothing works."""
        with patch(
            "db_mcp.connectors.api_discovery.requests.get",
            side_effect=Exception("Network error"),
        ):
            result = discover_api("https://api.example.com", {}, {}, 10.0)

        assert result.strategy == "none"
        assert len(result.endpoints) == 0
        assert len(result.errors) > 0

    def test_result_has_correct_structure(self):
        """DiscoveryResult should have all expected fields."""
        result = DiscoveryResult(
            endpoints=[],
            pagination=DiscoveredPagination(),
            strategy="none",
        )
        assert hasattr(result, "endpoints")
        assert hasattr(result, "pagination")
        assert hasattr(result, "spec_url")
        assert hasattr(result, "strategy")
        assert hasattr(result, "api_title")
        assert hasattr(result, "api_description")
        assert hasattr(result, "errors")
