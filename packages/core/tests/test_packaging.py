from pathlib import Path


def test_pyinstaller_spec_includes_connector_templates():
    spec_path = Path(__file__).resolve().parents[1] / "db-mcp.spec"
    spec_contents = spec_path.read_text()

    assert 'datas.append((str(templates_dir), "db_mcp/templates"))' in spec_contents
