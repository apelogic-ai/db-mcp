# Connector Templates

`db-mcp` ships built-in connector templates as single YAML files under:

`packages/core/src/db_mcp/static/connector_templates/`

The design goal is simple: for common integrations, a community contributor should be able to
add one new template file in one PR without touching Python code.

## Current Flow

- `db-mcp connector templates`
  Lists shipped templates.
- `db-mcp connector validate <path>`
  Validates either a plain `connector.yaml` contract or a full template file.
- `db-mcp init <name> --template <template-id>`
  Creates a new connection from a shipped template, prompts for `base_url` and required secrets,
  writes `connector.yaml`, and saves credentials into the connection-local `.env`.

## Template File Format

Each template is a single YAML document with:

```yaml
id: jira
title: Jira Cloud
description: Jira Cloud REST API for issue search and issue creation.
base_url_prompt: Jira base URL
env:
  - name: JIRA_EMAIL
    prompt: Jira email
    secret: false
  - name: JIRA_TOKEN
    prompt: Jira API token
    secret: true
connector:
  spec_version: 1.0.0
  type: api
  profile: api_openapi
  base_url: https://your-domain.atlassian.net
  auth:
    type: basic
    username_env: JIRA_EMAIL
    password_env: JIRA_TOKEN
  endpoints:
    - name: myself
      path: /rest/api/3/myself
      method: GET
```

## Contribution Rules

To keep template PRs single-file and low-friction:

- Put the whole template in one YAML file under
  `packages/core/src/db_mcp/static/connector_templates/`.
- Reuse existing connector contract capabilities only.
- Do not add Python code unless the target system requires runtime behavior that the current
  connector contract cannot express.
- Keep secrets out of the template. Use `env` prompts plus `*_env` references in the connector.
- Prefer conservative, read-first endpoints unless write support is clearly useful and safe.

## Validation

Before opening a PR, validate the template directly:

```bash
cd packages/core
uv run db-mcp connector validate src/db_mcp/static/connector_templates/<template>.yaml
```

You can also list the catalog locally:

```bash
cd packages/core
uv run db-mcp connector templates
```

## What Requires More Than One File

A template should stay single-file unless one of these is true:

- The integration needs new auth mechanics not already supported by the connector contract.
- The API needs new pagination or response handling behavior in the runtime.
- The UI or onboarding flow needs provider-specific affordances.

In those cases, the template file still belongs in `static/connector_templates/`, but the PR is
no longer expected to be single-file.
