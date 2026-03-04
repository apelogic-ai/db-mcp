"""Tests for init flow connector-type routing."""

from pathlib import Path

from db_mcp.cli.init_flow import _init_greenfield


def test_init_greenfield_api_flow_skips_database_url(monkeypatch, tmp_path):
    """Selecting API setup should avoid DATABASE_URL prompts."""
    from db_mcp.cli import init_flow

    called: dict[str, bool] = {}

    monkeypatch.setattr(
        "db_mcp.cli.agent_config.extract_database_url_from_claude_config",
        lambda _cfg: None,
    )
    monkeypatch.setattr(
        "db_mcp.cli.utils.load_claude_desktop_config",
        lambda: ({}, Path(tmp_path / "claude_desktop_config.json")),
    )
    monkeypatch.setattr(init_flow, "load_config", lambda: {})
    monkeypatch.setattr(
        init_flow, "get_connection_path", lambda _name: tmp_path / "analytics_connection"
    )
    monkeypatch.setattr(init_flow, "_configure_agents", lambda: None)
    monkeypatch.setattr(init_flow, "_offer_git_setup", lambda _name, _path: None)
    monkeypatch.setattr(init_flow.Confirm, "ask", lambda *args, **kwargs: False)
    monkeypatch.setattr(init_flow.Prompt, "ask", lambda *args, **kwargs: "api")
    monkeypatch.setattr(
        init_flow,
        "_prompt_and_save_database_url",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("DATABASE_URL prompt should not run for API setup")
        ),
    )

    def _fake_api_prompt(name: str) -> bool:
        called["api_prompt"] = True
        return True

    monkeypatch.setattr(
        init_flow,
        "_prompt_and_save_api_connection",
        _fake_api_prompt,
        raising=False,
    )

    _init_greenfield("analytics_connection")

    assert called["api_prompt"] is True
