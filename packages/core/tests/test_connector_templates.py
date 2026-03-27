from db_mcp.connector_templates import (
    get_connector_template,
    list_connector_templates,
    match_connector_template,
    materialize_connector_template,
)


def test_list_connector_templates_includes_builtins():
    templates = list_connector_templates()
    ids = {template.id for template in templates}

    assert {"jira", "dune", "superset", "metabase"}.issubset(ids)


def test_get_connector_template_returns_jira_descriptor():
    template = get_connector_template("jira")

    assert template is not None
    assert template.connector["type"] == "api"
    assert template.connector["profile"] == "api_openapi"
    assert template.connector["auth"]["type"] == "basic"
    assert any(endpoint["name"] == "create_issue" for endpoint in template.connector["endpoints"])
    assert [env_var.name for env_var in template.env] == ["JIRA_EMAIL", "JIRA_TOKEN"]


def test_get_connector_template_returns_metabase_descriptor():
    template = get_connector_template("metabase")

    assert template is not None
    assert template.connector["type"] == "api"
    assert template.connector["profile"] == "hybrid_bi"
    assert template.connector["auth"]["type"] == "header"
    assert template.connector["auth"]["header_name"] == "x-api-key"
    assert any(endpoint["name"] == "execute_sql" for endpoint in template.connector["endpoints"])
    assert [env_var.name for env_var in template.env] == ["X_API_KEY"]


def test_materialize_connector_template_overrides_base_url_and_env_names():
    connector = materialize_connector_template(
        "metabase",
        base_url="https://metabase.k8slens.dev",
        env_name_overrides={"X_API_KEY": "API_KEY"},
    )

    assert connector is not None
    assert connector["template_id"] == "metabase"
    assert connector["base_url"] == "https://metabase.k8slens.dev"
    assert connector["auth"]["token_env"] == "API_KEY"
    assert connector["auth"]["header_name"] == "x-api-key"
    assert any(endpoint["name"] == "execute_sql" for endpoint in connector["endpoints"])


def test_match_connector_template_identifies_metabase_shape():
    connector = materialize_connector_template("metabase")

    assert connector is not None
    assert match_connector_template(connector) == "metabase"


def test_match_connector_template_prefers_explicit_template_id_over_endpoint_drift():
    connector = materialize_connector_template("jira")

    assert connector is not None
    connector["endpoints"] = [
        {
            "name": "discovered_projects",
            "path": "/rest/api/3/project/search",
            "method": "GET",
        }
    ]

    assert match_connector_template(connector) == "jira"


def test_match_connector_template_identifies_legacy_jira_shape_without_template_id():
    connector = materialize_connector_template("jira")

    assert connector is not None
    connector.pop("template_id", None)
    connector["endpoints"] = connector["endpoints"] + [
        {
            "name": "projects_raw",
            "path": "/rest/api/3/project/search",
            "method": "GET",
            "response_mode": "raw",
        },
        {
            "name": "search_issues_raw",
            "path": "/rest/api/3/search/jql",
            "method": "GET",
            "response_mode": "raw",
        },
    ]

    assert match_connector_template(connector) == "jira"
