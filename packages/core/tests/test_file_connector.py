"""Tests for FileConnector — TDD tests written before implementation."""

import json
import textwrap

import duckdb
import pytest

from db_mcp.connectors import Connector
from db_mcp.connectors.file import FileConnector, FileConnectorConfig, FileSourceConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def csv_file(tmp_path):
    """Create a small CSV file."""
    path = tmp_path / "sales.csv"
    path.write_text(
        textwrap.dedent("""\
        id,product,amount,date
        1,Widget,9.99,2024-01-15
        2,Gadget,24.50,2024-02-20
        3,Widget,9.99,2024-03-10
    """)
    )
    return path


@pytest.fixture
def parquet_file(tmp_path):
    """Create a small Parquet file using DuckDB (no pyarrow needed)."""
    path = tmp_path / "events.parquet"
    conn = duckdb.connect()
    conn.execute(
        f"COPY (SELECT 1 AS id, 'click' AS event, 100 AS value "
        f"UNION ALL SELECT 2, 'view', 200) "
        f"TO '{path}' (FORMAT PARQUET)"
    )
    conn.close()
    return path


@pytest.fixture
def json_file(tmp_path):
    """Create a JSONL file."""
    path = tmp_path / "refunds.jsonl"
    lines = [
        json.dumps({"id": 1, "reason": "defective", "amount": 9.99}),
        json.dumps({"id": 2, "reason": "wrong_item", "amount": 24.50}),
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture
def multi_csv_dir(tmp_path):
    """Create a directory with multiple CSV files for glob testing."""
    parts = tmp_path / "parts"
    parts.mkdir()
    for i, name in enumerate(["part-001.csv", "part-002.csv"], start=1):
        (parts / name).write_text(f"id,value\n{i},{i * 10}\n")
    return parts


@pytest.fixture
def file_connector_config(tmp_path, csv_file, parquet_file, json_file):
    """Config with one source per file type."""
    return FileConnectorConfig(
        sources=[
            FileSourceConfig(name="sales", path=str(csv_file)),
            FileSourceConfig(name="events", path=str(parquet_file)),
            FileSourceConfig(name="refunds", path=str(json_file)),
        ]
    )


@pytest.fixture
def file_connector(file_connector_config):
    """A FileConnector instance."""
    return FileConnector(file_connector_config)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestFileConnectorConfig:
    def test_type_is_file(self):
        config = FileConnectorConfig(sources=[])
        assert config.type == "file"

    def test_sources_from_list(self, csv_file):
        config = FileConnectorConfig(sources=[FileSourceConfig(name="t", path=str(csv_file))])
        assert len(config.sources) == 1
        assert config.sources[0].name == "t"


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


class TestFileConnectorProtocol:
    def test_satisfies_connector_protocol(self, file_connector):
        assert isinstance(file_connector, Connector)

    def test_has_all_protocol_methods(self, file_connector):
        for method in [
            "test_connection",
            "get_dialect",
            "get_catalogs",
            "get_schemas",
            "get_tables",
            "get_columns",
            "get_table_sample",
            "execute_sql",
        ]:
            assert hasattr(file_connector, method), f"Missing method: {method}"


# ---------------------------------------------------------------------------
# test_connection tests
# ---------------------------------------------------------------------------


class TestFileConnectorTestConnection:
    def test_connection_success(self, file_connector):
        result = file_connector.test_connection()
        assert result["connected"] is True
        assert result["error"] is None

    def test_connection_missing_file(self, tmp_path):
        config = FileConnectorConfig(
            sources=[FileSourceConfig(name="missing", path=str(tmp_path / "nope.csv"))]
        )
        conn = FileConnector(config)
        result = conn.test_connection()
        assert result["connected"] is False
        assert result["error"] is not None

    def test_connection_glob_matches(self, multi_csv_dir):
        config = FileConnectorConfig(
            sources=[FileSourceConfig(name="parts", path=str(multi_csv_dir / "*.csv"))]
        )
        conn = FileConnector(config)
        result = conn.test_connection()
        assert result["connected"] is True
        assert result["sources"]["parts"] == 2

    def test_connection_glob_no_matches(self, tmp_path):
        config = FileConnectorConfig(
            sources=[FileSourceConfig(name="empty", path=str(tmp_path / "*.parquet"))]
        )
        conn = FileConnector(config)
        result = conn.test_connection()
        assert result["connected"] is False


# ---------------------------------------------------------------------------
# Dialect / catalogs / schemas tests
# ---------------------------------------------------------------------------


class TestFileConnectorDialect:
    def test_get_dialect(self, file_connector):
        assert file_connector.get_dialect() == "duckdb"


class TestFileConnectorCatalogsSchemas:
    def test_get_catalogs(self, file_connector):
        assert file_connector.get_catalogs() == [None]

    def test_get_schemas(self, file_connector):
        assert file_connector.get_schemas() == [None]


# ---------------------------------------------------------------------------
# Tables tests
# ---------------------------------------------------------------------------


class TestFileConnectorTables:
    def test_get_tables_returns_all_sources(self, file_connector):
        tables = file_connector.get_tables()
        names = {t["name"] for t in tables}
        assert names == {"sales", "events", "refunds"}

    def test_table_type_is_view(self, file_connector):
        tables = file_connector.get_tables()
        for t in tables:
            assert t["type"] == "view"

    def test_table_has_required_keys(self, file_connector):
        tables = file_connector.get_tables()
        for t in tables:
            assert "name" in t
            assert "schema" in t
            assert "catalog" in t
            assert "full_name" in t


# ---------------------------------------------------------------------------
# Columns tests
# ---------------------------------------------------------------------------


class TestFileConnectorColumns:
    def test_get_columns_csv(self, file_connector):
        cols = file_connector.get_columns("sales")
        col_names = [c["name"] for c in cols]
        assert "id" in col_names
        assert "product" in col_names
        assert "amount" in col_names
        assert "date" in col_names

    def test_get_columns_parquet(self, file_connector):
        cols = file_connector.get_columns("events")
        col_names = [c["name"] for c in cols]
        assert "id" in col_names
        assert "event" in col_names
        assert "value" in col_names

    def test_get_columns_json(self, file_connector):
        cols = file_connector.get_columns("refunds")
        col_names = [c["name"] for c in cols]
        assert "id" in col_names
        assert "reason" in col_names
        assert "amount" in col_names

    def test_get_columns_has_type(self, file_connector):
        cols = file_connector.get_columns("sales")
        for c in cols:
            assert "type" in c
            assert "nullable" in c

    def test_get_columns_unknown_table(self, file_connector):
        with pytest.raises(Exception):
            file_connector.get_columns("nonexistent")


# ---------------------------------------------------------------------------
# Sample tests
# ---------------------------------------------------------------------------


class TestFileConnectorSample:
    def test_get_table_sample_csv(self, file_connector):
        rows = file_connector.get_table_sample("sales")
        assert len(rows) == 3  # all 3 rows (default limit=5)
        assert "product" in rows[0]

    def test_get_table_sample_parquet(self, file_connector):
        rows = file_connector.get_table_sample("events")
        assert len(rows) == 2

    def test_get_table_sample_limit(self, file_connector):
        rows = file_connector.get_table_sample("sales", limit=1)
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# execute_sql tests
# ---------------------------------------------------------------------------


class TestFileConnectorExecuteSQL:
    def test_execute_sql_select(self, file_connector):
        rows = file_connector.execute_sql("SELECT * FROM sales")
        assert len(rows) == 3

    def test_execute_sql_aggregation(self, file_connector):
        rows = file_connector.execute_sql("SELECT COUNT(*) AS cnt FROM sales")
        assert rows[0]["cnt"] == 3

    def test_execute_sql_join(self, file_connector):
        sql = "SELECT s.product, r.reason FROM sales s JOIN refunds r ON s.amount = r.amount"
        rows = file_connector.execute_sql(sql)
        assert len(rows) > 0

    def test_execute_sql_invalid(self, file_connector):
        with pytest.raises(Exception):
            file_connector.execute_sql("SELECT * FROM nonexistent_table")


# ---------------------------------------------------------------------------
# Format detection tests
# ---------------------------------------------------------------------------


class TestFileFormatDetection:
    def test_csv_extension(self):
        from db_mcp.connectors.file import _read_function_for_path

        assert _read_function_for_path("/data/sales.csv") == "read_csv_auto"

    def test_tsv_extension(self):
        from db_mcp.connectors.file import _read_function_for_path

        assert _read_function_for_path("/data/sales.tsv") == "read_csv_auto"

    def test_parquet_extension(self):
        from db_mcp.connectors.file import _read_function_for_path

        assert _read_function_for_path("/data/events.parquet") == "read_parquet"

    def test_json_extension(self):
        from db_mcp.connectors.file import _read_function_for_path

        assert _read_function_for_path("/data/refunds.json") == "read_json_auto"

    def test_jsonl_extension(self):
        from db_mcp.connectors.file import _read_function_for_path

        assert _read_function_for_path("/data/refunds.jsonl") == "read_json_auto"

    def test_ndjson_extension(self):
        from db_mcp.connectors.file import _read_function_for_path

        assert _read_function_for_path("/data/refunds.ndjson") == "read_json_auto"

    def test_unsupported_extension(self):
        from db_mcp.connectors.file import _read_function_for_path

        with pytest.raises(ValueError):
            _read_function_for_path("/data/file.xlsx")

    def test_glob_path_extension(self):
        from db_mcp.connectors.file import _read_function_for_path

        assert _read_function_for_path("/data/events/*.parquet") == "read_parquet"


# ---------------------------------------------------------------------------
# Glob source tests
# ---------------------------------------------------------------------------


class TestFileConnectorGlob:
    def test_glob_csv_sources(self, multi_csv_dir):
        config = FileConnectorConfig(
            sources=[FileSourceConfig(name="parts", path=str(multi_csv_dir / "*.csv"))]
        )
        conn = FileConnector(config)
        rows = conn.execute_sql("SELECT * FROM parts ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["id"] == 1
        assert rows[1]["id"] == 2

    def test_glob_csv_columns(self, multi_csv_dir):
        config = FileConnectorConfig(
            sources=[FileSourceConfig(name="parts", path=str(multi_csv_dir / "*.csv"))]
        )
        conn = FileConnector(config)
        cols = conn.get_columns("parts")
        col_names = [c["name"] for c in cols]
        assert "id" in col_names
        assert "value" in col_names


# ---------------------------------------------------------------------------
# Directory mode tests
# ---------------------------------------------------------------------------


class TestFileConnectorDirectoryMode:
    """Test auto-discovery of files from a directory."""

    @pytest.fixture
    def data_dir(self, tmp_path):
        """Create a directory with mixed file types."""
        d = tmp_path / "data"
        d.mkdir()
        # CSV
        (d / "sales.csv").write_text("id,product,amount\n1,Widget,9.99\n2,Gadget,24.50\n")
        # Another CSV
        (d / "orders.csv").write_text("id,customer,total\n1,Alice,100\n")
        # JSON
        (d / "config.json").write_text('[{"key": "val"}]\n')
        # Unsupported file (should be ignored)
        (d / "notes.txt").write_text("some notes\n")
        # Hidden file (should be ignored)
        (d / ".hidden.csv").write_text("id\n1\n")
        return d

    @pytest.fixture
    def parquet_dir(self, tmp_path):
        """Create a directory with parquet files."""
        d = tmp_path / "parquet_data"
        d.mkdir()
        conn = duckdb.connect()
        conn.execute(
            f"COPY (SELECT 1 AS id, 'a' AS name) TO '{d / 'users.parquet'}' (FORMAT PARQUET)"
        )
        conn.execute(
            f"COPY (SELECT 10 AS id, 'x' AS item) TO '{d / 'items.parquet'}' (FORMAT PARQUET)"
        )
        conn.close()
        return d

    def test_directory_discovers_csv_files(self, data_dir):
        config = FileConnectorConfig(directory=str(data_dir))
        conn = FileConnector(config)
        tables = conn.get_tables()
        names = {t["name"] for t in tables}
        assert "sales" in names
        assert "orders" in names

    def test_directory_discovers_json_files(self, data_dir):
        config = FileConnectorConfig(directory=str(data_dir))
        conn = FileConnector(config)
        names = {t["name"] for t in conn.get_tables()}
        assert "config" in names

    def test_directory_ignores_unsupported_extensions(self, data_dir):
        config = FileConnectorConfig(directory=str(data_dir))
        conn = FileConnector(config)
        names = {t["name"] for t in conn.get_tables()}
        assert "notes" not in names

    def test_directory_ignores_hidden_files(self, data_dir):
        config = FileConnectorConfig(directory=str(data_dir))
        conn = FileConnector(config)
        names = {t["name"] for t in conn.get_tables()}
        assert ".hidden" not in names
        assert "hidden" not in names

    def test_directory_query_works(self, data_dir):
        config = FileConnectorConfig(directory=str(data_dir))
        conn = FileConnector(config)
        rows = conn.execute_sql("SELECT * FROM sales")
        assert len(rows) == 2
        assert rows[0]["product"] == "Widget"

    def test_directory_columns_work(self, data_dir):
        config = FileConnectorConfig(directory=str(data_dir))
        conn = FileConnector(config)
        cols = conn.get_columns("orders")
        col_names = [c["name"] for c in cols]
        assert "customer" in col_names

    def test_directory_test_connection(self, data_dir):
        config = FileConnectorConfig(directory=str(data_dir))
        conn = FileConnector(config)
        result = conn.test_connection()
        assert result["connected"] is True

    def test_directory_parquet(self, parquet_dir):
        config = FileConnectorConfig(directory=str(parquet_dir))
        conn = FileConnector(config)
        tables = conn.get_tables()
        names = {t["name"] for t in tables}
        assert "users" in names
        assert "items" in names
        rows = conn.execute_sql("SELECT * FROM users")
        assert rows[0]["name"] == "a"

    def test_directory_cross_table_join(self, data_dir):
        config = FileConnectorConfig(directory=str(data_dir))
        conn = FileConnector(config)
        rows = conn.execute_sql(
            "SELECT s.product, o.customer FROM sales s JOIN orders o ON s.id = o.id"
        )
        assert len(rows) == 1

    def test_directory_empty_raises_no_error(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        config = FileConnectorConfig(directory=str(d))
        conn = FileConnector(config)
        tables = conn.get_tables()
        assert tables == []

    def test_directory_nonexistent(self, tmp_path):
        config = FileConnectorConfig(directory=str(tmp_path / "nope"))
        conn = FileConnector(config)
        result = conn.test_connection()
        assert result["connected"] is False

    def test_directory_combined_with_sources(self, data_dir, tmp_path):
        """Directory sources and explicit sources can be combined."""
        extra = tmp_path / "extra.csv"
        extra.write_text("id,color\n1,red\n")
        config = FileConnectorConfig(
            directory=str(data_dir),
            sources=[FileSourceConfig(name="extra", path=str(extra))],
        )
        conn = FileConnector(config)
        names = {t["name"] for t in conn.get_tables()}
        assert "sales" in names  # from directory
        assert "extra" in names  # from explicit source
