# Metabase `lens` Runtime Debug Note

## Summary

The current failure on the `lens` connection is **not** a `connector.yaml` parsing problem.

`db-mcp doctor -c lens --json` shows:

- `load_connector: pass`
- `auth: pass`
- `execute_test: fail`
- error: `Expecting value: line 1 column 1 (char 0)`

That means:

1. The connection YAML loaded successfully.
2. The Metabase connector authenticated successfully.
3. The failure is happening during SQL execution against `/api/dataset`.
4. The immediate error is a JSON parse failure on the response body.

## What Has Been Ruled Out

The following earlier diagnoses are not consistent with the observed runtime behavior:

- `body_template` causing connector initialization failure
- endpoint `description` causing `APIEndpointConfig.__init__()` failure
- pagination `offset_param` causing `APIPaginationConfig` failure

If any of those were still the active problem, `load_connector` would fail. It does not.

## Verified Local Binary State

The installed local binary reports `0.8.12` and was inspected directly as a frozen PyInstaller bundle.

The embedded runtime includes the expected compatibility code:

- `db_mcp.connectors.api`
- `db_mcp.connectors`
- `db_mcp.connector_compat`
- `db_mcp.connector_plugins.builtin.metabase`

The embedded code includes:

- `APIEndpointConfig.description`
- `APIEndpointConfig.body_template`
- `APIPaginationConfig.offset_param`
- Metabase payload normalization that strips legacy `body_template` and endpoint `description`

So the current failure is downstream of YAML loading and connector construction.

## Current Working Diagnosis

`execute_sql()` posts to Metabase `/api/dataset` and then immediately calls `resp.json()`.

The observed error:

`Expecting value: line 1 column 1 (char 0)`

strongly suggests that the response body is one of:

- empty
- HTML
- plaintext
- some non-JSON proxy or auth response

This is the important distinction:

- the request is reaching the SQL execution path
- the response content is not valid JSON for the current parser

## Likely Causes

Most likely causes, in order:

1. A reverse proxy or auth layer is returning HTML instead of JSON.
2. Metabase is returning an empty body on a nominally successful response.
3. Metabase is returning a non-JSON error page even though HTTP status handling passed.
4. The request payload shape is accepted at transport level but not producing a JSON response body.

## Next Diagnostic

The next step should capture the actual `/api/dataset` response details from the installed binary runtime:

- request URL
- request body
- HTTP status code
- `content-type`
- first part of raw response text

That diagnostic should be treated as the source of truth, not the agent’s textual interpretation.

## Interpretation Guide

When that response is captured, use this mapping:

- `content-type: text/html`
  - most likely a proxy, SSO, or login page
- empty response body
  - likely blank upstream/proxy response or unexpected Metabase behavior
- JSON body with an error object
  - request reached Metabase correctly; parser/handling can be adjusted based on returned payload
- non-2xx with HTML/plaintext
  - transport path is wrong or being intercepted before normal Metabase JSON handling

## Bottom Line

As of this investigation, the active problem is:

**Metabase SQL execution is failing because the `/api/dataset` response is not valid JSON for the current runtime parser.**

It is **not** currently evidenced as a `connector.yaml` field compatibility problem.
