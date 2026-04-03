"""Verify inject_protocol lives in tools/protocol.py, not tools/shell.py."""



def test_inject_protocol_importable_from_protocol_module():
    """tools/protocol.py must be the canonical home of inject_protocol."""
    from db_mcp.tools.protocol import inject_protocol
    assert callable(inject_protocol)


def test_shell_still_re_exports_inject_protocol():
    """tools/shell.py must re-export inject_protocol for backward compat."""
    from db_mcp.tools.shell import inject_protocol
    assert callable(inject_protocol)


def test_both_refer_to_same_object():
    """shell and protocol must export the same function, not a copy."""
    from db_mcp.tools.protocol import inject_protocol as proto_fn
    from db_mcp.tools.shell import inject_protocol as shell_fn
    assert proto_fn is shell_fn


def test_inject_protocol_not_defined_in_shell_source():
    """The definition must live in protocol.py, not shell.py."""
    import inspect

    from db_mcp.tools.protocol import inject_protocol
    src_file = inspect.getfile(inject_protocol)
    assert src_file.endswith("protocol.py"), (
        f"inject_protocol is defined in {src_file!r}, expected protocol.py"
    )


def test_services_have_no_inject_protocol():
    """services/ must never call inject_protocol — it is an MCP presentation concern."""
    import os
    services_dir = os.path.join(
        os.path.dirname(__file__), "..", "src", "db_mcp", "services"
    )
    for fname in os.listdir(services_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(services_dir, fname)
        src = open(path).read()
        assert "inject_protocol" not in src, (
            f"services/{fname} uses inject_protocol — must not reach into MCP layer"
        )


def test_gateway_has_no_inject_protocol():
    """gateway/ must never call inject_protocol."""
    import os

    import db_mcp_data.gateway as _gw
    gateway_dir = os.path.dirname(_gw.__file__)
    for fname in os.listdir(gateway_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(gateway_dir, fname)
        src = open(path).read()
        assert "inject_protocol" not in src, (
            f"gateway/{fname} uses inject_protocol — must not reach into MCP layer"
        )
