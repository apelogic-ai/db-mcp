from db_mcp.connector_templates import get_connector_template, list_connector_templates


def test_list_connector_templates_includes_builtins():
    templates = list_connector_templates()
    ids = {template.id for template in templates}

    assert {"jira", "dune", "superset"}.issubset(ids)


def test_get_connector_template_returns_jira_descriptor():
    template = get_connector_template("jira")

    assert template is not None
    assert template.connector["type"] == "api"
    assert template.connector["profile"] == "api_openapi"
    assert template.connector["auth"]["type"] == "basic"
    assert any(endpoint["name"] == "create_issue" for endpoint in template.connector["endpoints"])
    assert [env_var.name for env_var in template.env] == ["JIRA_EMAIL", "JIRA_TOKEN"]
