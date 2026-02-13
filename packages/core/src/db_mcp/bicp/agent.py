"""BICP Agent implementation for db-mcp.

This module provides a BICP (Business Intelligence Client Protocol) agent
that integrates with db-mcp's existing infrastructure for SQL generation,
validation, and execution.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from bicp_agent import (
    BICPAgent,
    ColumnInfo,
    QueryCandidate,
    QueryCost,
    SchemaDescribeParams,
    SchemaDescribeResult,
    SchemaInfo,
    SchemaListParams,
    SchemaListResult,
    SemanticObjectType,
    SemanticSearchMatch,
    SemanticSearchParams,
    SemanticSearchResult,
    ServerCapabilities,
    Session,
    TableInfo,
)
from bicp_agent.session import QueryState
from sqlalchemy import text

from db_mcp.config import get_settings
from db_mcp.connectors import get_connector
from db_mcp.connectors.sql import SQLConnector
from db_mcp.onboarding.schema_store import load_schema_descriptions
from db_mcp.training.store import load_examples
from db_mcp.validation.explain import ExplainResult, explain_sql, validate_read_only

logger = logging.getLogger(__name__)


class DBMCPAgent(BICPAgent):
    """BICP Agent backed by db-mcp infrastructure.

    This agent implements the BICP protocol using db-mcp's existing
    components for database introspection, SQL generation, validation,
    and execution.

    Example:
        agent = DBMCPAgent()
        agent.serve(port=8080)
    """

    def __init__(
        self,
        name: str = "db-mcp BICP Agent",
        version: str = "0.1.0",
    ) -> None:
        # Determine capabilities based on db-mcp configuration
        settings = get_settings()
        dialect = self._detect_dialect()

        capabilities = ServerCapabilities(
            streaming=False,  # v0.1: synchronous execution only
            candidate_generation=True,
            semantic_layer=True,  # We have schema descriptions and examples
            refinement=True,
            dialects=[dialect] if dialect else [],
            max_concurrent_queries=5,
        )

        super().__init__(name=name, version=version, capabilities=capabilities)

        self._settings = settings
        self._dialect = dialect

        # Register custom method handlers
        self._method_handlers["connections/list"] = self._handle_connections_list
        self._method_handlers["connections/switch"] = self._handle_connections_switch
        self._method_handlers["connections/create"] = self._handle_connections_create
        self._method_handlers["connections/test"] = self._handle_connections_test
        self._method_handlers["connections/delete"] = self._handle_connections_delete
        self._method_handlers["connections/get"] = self._handle_connections_get
        self._method_handlers["connections/update"] = self._handle_connections_update

        # Context viewer handlers
        self._method_handlers["context/tree"] = self._handle_context_tree
        self._method_handlers["context/usage"] = self._handle_context_usage
        self._method_handlers["context/read"] = self._handle_context_read
        self._method_handlers["context/write"] = self._handle_context_write
        self._method_handlers["context/create"] = self._handle_context_create
        self._method_handlers["context/delete"] = self._handle_context_delete
        self._method_handlers["context/add-rule"] = self._handle_context_add_rule

        # Git history handlers
        self._method_handlers["context/git/history"] = self._handle_git_history
        self._method_handlers["context/git/show"] = self._handle_git_show
        self._method_handlers["context/git/revert"] = self._handle_git_revert

        # Trace viewer handlers
        self._method_handlers["traces/list"] = self._handle_traces_list
        self._method_handlers["traces/clear"] = self._handle_traces_clear
        self._method_handlers["traces/dates"] = self._handle_traces_dates

        # Insights handlers
        self._method_handlers["insights/analyze"] = self._handle_insights_analyze
        self._method_handlers["gaps/dismiss"] = self._handle_gaps_dismiss
        self._method_handlers["insights/save-example"] = self._handle_insights_save_example

        # Metrics & dimensions handlers
        self._method_handlers["metrics/list"] = self._handle_metrics_list
        self._method_handlers["metrics/add"] = self._handle_metrics_add
        self._method_handlers["metrics/update"] = self._handle_metrics_update
        self._method_handlers["metrics/delete"] = self._handle_metrics_delete
        self._method_handlers["metrics/candidates"] = self._handle_metrics_candidates
        self._method_handlers["metrics/approve"] = self._handle_metrics_approve

        # API connector handlers
        self._method_handlers["connections/sync"] = self._handle_connections_sync
        self._method_handlers["connections/discover"] = self._handle_connections_discover

        # Agent configuration handlers
        self._method_handlers["agents/list"] = self._handle_agents_list
        self._method_handlers["agents/configure"] = self._handle_agents_configure
        self._method_handlers["agents/remove"] = self._handle_agents_remove
        self._method_handlers["agents/config-snippet"] = self._handle_agents_config_snippet
        self._method_handlers["agents/config-write"] = self._handle_agents_config_write

        # Schema explorer handlers
        self._method_handlers["schema/catalogs"] = self._handle_schema_catalogs
        self._method_handlers["schema/schemas"] = self._handle_schema_schemas
        self._method_handlers["schema/tables"] = self._handle_schema_tables
        self._method_handlers["schema/columns"] = self._handle_schema_columns
        self._method_handlers["schema/validate-link"] = self._handle_schema_validate_link

    def _detect_dialect(self) -> str:
        """Detect the database dialect from configuration."""
        try:
            connector = get_connector()
            return connector.get_dialect()
        except Exception:
            return "unknown"

    # ========== Required Methods ==========

    async def generate_candidates(
        self, session: Session, query: QueryState
    ) -> list[QueryCandidate]:
        """Generate SQL candidates for a natural language query.

        Uses db-mcp's schema context and training examples to generate
        SQL candidates. For v0.1, we generate a single candidate using
        the schema context - more sophisticated generation can be added later.

        Args:
            session: The current BICP session
            query: The query state with natural_language set

        Returns:
            List of QueryCandidate objects
        """
        provider_id = self._settings.provider_id
        intent = query.natural_language

        # Load schema context
        schema = load_schema_descriptions(provider_id)
        if not schema:
            # Return empty candidate list if no schema
            return [
                QueryCandidate(
                    candidate_id=str(uuid.uuid4())[:8],
                    sql="-- Schema not configured. Complete onboarding first.",
                    explanation="No schema descriptions found.",
                    confidence=0.0,
                    tables_used=[],
                    warnings=["Schema onboarding required before generating queries."],
                )
            ]

        # Load training examples for context
        examples = load_examples(provider_id)

        # Build context for SQL generation
        # For v0.1, we return context that helps the client generate SQL
        # A more sophisticated implementation would use an LLM here

        # Find relevant tables based on intent keywords
        intent_lower = intent.lower()
        relevant_tables = []
        for table in schema.tables:
            table_name_lower = (table.name or "").lower()
            desc_lower = (table.description or "").lower()

            # Simple keyword matching
            if table_name_lower in intent_lower or intent_lower in table_name_lower:
                relevant_tables.append(table)
            elif any(word in desc_lower for word in intent_lower.split() if len(word) > 3):
                relevant_tables.append(table)

        # If no relevant tables found, use all documented tables
        if not relevant_tables:
            relevant_tables = [t for t in schema.tables if t.description][:5]

        # Find similar examples
        similar_examples = []
        for ex in examples.examples:
            ex_lower = ex.natural_language.lower()
            if any(word in ex_lower for word in intent_lower.split() if len(word) > 3):
                similar_examples.append(ex)

        # Build a template SQL based on context
        # This is a placeholder - real implementation would use LLM
        tables_used = [t.full_name or t.name for t in relevant_tables]

        # Generate candidate with context
        explanation_parts = [f"Query intent: {intent}"]
        if relevant_tables:
            explanation_parts.append(
                f"Relevant tables: {', '.join(t.name for t in relevant_tables[:3])}"
            )
        if similar_examples:
            explanation_parts.append(f"Similar examples found: {len(similar_examples)}")

        # For v0.1, provide a template/placeholder
        # The client (or future versions) will generate actual SQL
        if similar_examples:
            # Use the most similar example as a starting point
            best_example = similar_examples[0]
            candidate_sql = best_example.sql
            confidence = 0.7
        elif relevant_tables:
            # Generate a basic SELECT template
            table = relevant_tables[0]
            cols = ", ".join(c.name for c in (table.columns or [])[:5])
            candidate_sql = f"SELECT {cols or '*'} FROM {table.full_name or table.name} LIMIT 100"
            confidence = 0.3
        else:
            candidate_sql = "-- Unable to generate SQL. Please provide more context."
            confidence = 0.0

        # Validate the SQL if we have one
        warnings = []
        cost: QueryCost | None = None

        if not candidate_sql.startswith("--"):
            is_valid, error = validate_read_only(candidate_sql)
            if not is_valid:
                warnings.append(f"Validation warning: {error}")

            # Get cost estimate
            try:
                explain_result: ExplainResult = explain_sql(candidate_sql)
                if explain_result.valid:
                    cost = QueryCost(
                        estimated_rows=explain_result.estimated_rows,
                        cost_units=explain_result.estimated_cost,
                    )
                else:
                    warnings.append(f"Cost estimation failed: {explain_result.error}")
            except Exception as e:
                warnings.append(f"Cost estimation error: {e}")

        candidate = QueryCandidate(
            candidate_id=str(uuid.uuid4())[:8],
            sql=candidate_sql,
            explanation="; ".join(explanation_parts),
            confidence=confidence,
            estimated_cost=cost,
            tables_used=tables_used[:5],
            warnings=warnings,
        )

        return [candidate]

    async def execute_query(
        self, session: Session, query: QueryState
    ) -> tuple[list[dict[str, Any]], list[list[Any]]]:
        """Execute an approved SQL query.

        Uses SQLAlchemy to execute the query via db-mcp's connection manager.

        Args:
            session: The current BICP session
            query: The query state with final_sql set

        Returns:
            Tuple of (columns, rows) where columns is list of {"name": str, "dataType": str}
        """
        sql = query.final_sql
        if not sql:
            raise ValueError("No SQL to execute")

        # Validate read-only
        is_valid, error = validate_read_only(sql)
        if not is_valid:
            raise ValueError(f"Query validation failed: {error}")

        start_time = time.time()

        try:
            connector = get_connector()

            if isinstance(connector, SQLConnector):
                engine = connector.get_engine()
                with engine.connect() as conn:
                    result = conn.execute(text(sql))
                    column_names = list(result.keys())
                    columns = [{"name": name, "dataType": "VARCHAR"} for name in column_names]
                    rows = []
                    for i, row in enumerate(result):
                        if i >= 10000:
                            break
                        rows.append(list(row))
            else:
                # FileConnector / APIConnector — use execute_sql
                result_rows = connector.execute_sql(sql)
                if result_rows:
                    columns = [{"name": k, "dataType": "VARCHAR"} for k in result_rows[0].keys()]
                    rows = [list(r.values()) for r in result_rows[:10000]]
                else:
                    columns = []
                    rows = []

            query.execution_time_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Query executed: {len(rows)} rows in {query.execution_time_ms}ms")
            return columns, rows

        except Exception as e:
            logger.exception(f"Query execution failed: {e}")
            raise

    # ========== Optional Methods ==========

    async def list_schemas(self, params: SchemaListParams) -> SchemaListResult:
        """List available schemas in the database.

        Uses db-mcp's introspection to list catalogs and schemas.
        """
        try:
            connector = get_connector()
            catalog = params.catalog
            schemas_list = []

            if catalog:
                # List schemas in specific catalog
                schema_names = connector.get_schemas(catalog=catalog)
                for name in schema_names:
                    if name:
                        # Get table count for this schema
                        try:
                            tables = connector.get_tables(schema=name, catalog=catalog)
                            table_count = len(tables)
                        except Exception:
                            table_count = None

                        schemas_list.append(
                            SchemaInfo(
                                catalog=catalog,
                                schema_=name,
                                table_count=table_count,
                            )
                        )
            else:
                # List all catalogs and their schemas
                catalogs = connector.get_catalogs()
                for cat in catalogs:
                    schema_names = connector.get_schemas(catalog=cat)
                    for name in schema_names:
                        if name:
                            schemas_list.append(
                                SchemaInfo(
                                    catalog=cat,
                                    schema_=name,
                                )
                            )

            return SchemaListResult(schemas=schemas_list)

        except Exception as e:
            logger.exception(f"Failed to list schemas: {e}")
            return SchemaListResult(schemas=[])

    async def describe_schema(self, params: SchemaDescribeParams) -> SchemaDescribeResult:
        """Describe tables in a schema.

        Uses db-mcp's introspection and schema descriptions.
        """
        schema_name = params.schema_
        catalog = params.catalog
        include_columns = params.include_columns

        try:
            connector = get_connector()
            # Get tables from database
            tables = connector.get_tables(schema=schema_name, catalog=catalog)

            # Load schema descriptions if available
            provider_id = self._settings.provider_id
            schema_desc = load_schema_descriptions(provider_id)
            desc_by_name = {}
            if schema_desc:
                for t in schema_desc.tables:
                    desc_by_name[t.full_name or t.name] = t

            table_infos = []
            for table in tables:
                full_name = table.get("full_name", table["name"])
                desc_table = desc_by_name.get(full_name)

                columns = []
                if include_columns:
                    try:
                        col_data = connector.get_columns(
                            table["name"],
                            schema=schema_name,
                            catalog=catalog,
                        )
                        for col in col_data:
                            # Get description from schema store
                            col_desc = None
                            if desc_table:
                                for dc in desc_table.columns or []:
                                    if dc.name == col["name"]:
                                        col_desc = dc.description
                                        break

                            columns.append(
                                ColumnInfo(
                                    name=col["name"],
                                    data_type=col.get("type", "VARCHAR"),
                                    nullable=col.get("nullable", True),
                                    description=col_desc,
                                    is_primary_key=col.get("primary_key", False),
                                )
                            )
                    except Exception as e:
                        logger.warning(f"Failed to get columns for {full_name}: {e}")

                table_infos.append(
                    TableInfo(
                        name=table["name"],
                        description=desc_table.description if desc_table else None,
                        columns=columns,
                    )
                )

            return SchemaDescribeResult(
                schema_=schema_name,
                catalog=catalog,
                tables=table_infos,
            )

        except Exception as e:
            logger.exception(f"Failed to describe schema: {e}")
            return SchemaDescribeResult(
                schema_=schema_name,
                catalog=catalog,
                tables=[],
            )

    async def semantic_search(self, params: SemanticSearchParams) -> SemanticSearchResult:
        """Search through training examples and domain model.

        Provides semantic search over:
        - Table descriptions
        - Column descriptions
        - Query examples
        """
        query = params.query.lower()
        object_types = params.object_types
        limit = params.limit

        provider_id = self._settings.provider_id
        results: list[SemanticSearchMatch] = []

        # Search tables and columns
        if SemanticObjectType.TABLE in object_types or SemanticObjectType.COLUMN in object_types:
            schema = load_schema_descriptions(provider_id)
            if schema:
                for table in schema.tables:
                    # Search table names and descriptions
                    if SemanticObjectType.TABLE in object_types:
                        score = self._compute_match_score(
                            query,
                            table.name,
                            table.description,
                        )
                        if score > 0.1:
                            results.append(
                                SemanticSearchMatch(
                                    type=SemanticObjectType.TABLE,
                                    name=table.full_name or table.name,
                                    description=table.description,
                                    score=score,
                                )
                            )

                    # Search columns
                    if SemanticObjectType.COLUMN in object_types:
                        for col in table.columns or []:
                            score = self._compute_match_score(
                                query,
                                col.name,
                                col.description,
                            )
                            if score > 0.1:
                                results.append(
                                    SemanticSearchMatch(
                                        type=SemanticObjectType.COLUMN,
                                        name=col.name,
                                        description=col.description,
                                        score=score,
                                        parent=table.full_name or table.name,
                                    )
                                )

        # Search examples (as metrics/dimensions)
        if SemanticObjectType.METRIC in object_types:
            examples = load_examples(provider_id)
            for ex in examples.examples:
                score = self._compute_match_score(
                    query,
                    ex.natural_language,
                    ex.notes,
                )
                if score > 0.1:
                    results.append(
                        SemanticSearchMatch(
                            type=SemanticObjectType.METRIC,
                            name=ex.natural_language[:50],
                            description=ex.sql[:100],
                            score=score,
                            tags=ex.tags or [],
                        )
                    )

        # Sort by score and limit
        results.sort(key=lambda x: x.score, reverse=True)
        return SemanticSearchResult(results=results[:limit])

    def _compute_match_score(
        self,
        query: str,
        name: str | None,
        description: str | None,
    ) -> float:
        """Compute a simple keyword-based match score.

        For v0.1, uses basic keyword matching. Future versions could
        use embeddings for semantic similarity.
        """
        if not name and not description:
            return 0.0

        query_words = set(query.lower().split())
        score = 0.0

        # Match against name
        if name:
            name_lower = name.lower()
            name_words = set(name_lower.replace("_", " ").split())

            # Exact substring match
            if query in name_lower:
                score += 0.5

            # Word overlap
            overlap = len(query_words & name_words)
            if overlap > 0:
                score += 0.3 * (overlap / len(query_words))

        # Match against description
        if description:
            desc_lower = description.lower()
            desc_words = set(desc_lower.split())

            # Exact substring match
            if query in desc_lower:
                score += 0.3

            # Word overlap
            overlap = len(query_words & desc_words)
            if overlap > 0:
                score += 0.2 * (overlap / len(query_words))

        return min(score, 1.0)

    async def on_session_created(self, session: Session) -> None:
        """Log session creation."""
        logger.info(f"BICP session created: {session.session_id}")

    async def on_query_approved(self, session: Session, query: QueryState) -> None:
        """Log query approval."""
        sql_preview = query.final_sql[:100] if query.final_sql else "N/A"
        logger.info(f"Query approved: {query.query_id}, SQL: {sql_preview}...")

    # ========== Custom Methods (db-mcp specific) ==========

    async def _handle_connections_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """List all configured db-mcp connections.

        Returns connection metadata including:
        - name: Connection identifier
        - isActive: Whether this is the currently active connection
        - hasSchema: Whether schema descriptions exist
        - hasDomain: Whether domain model exists
        - hasCredentials: Whether .env file exists
        - dialect: Database dialect (if detectable)
        """
        connections_dir = Path.home() / ".db-mcp" / "connections"
        config_file = Path.home() / ".db-mcp" / "config.yaml"

        # Get active connection from config
        active_connection = None
        if config_file.exists():
            import yaml

            with open(config_file) as f:
                config = yaml.safe_load(f) or {}
                active_connection = config.get("active_connection")

        connections = []
        if connections_dir.exists():
            for conn_path in sorted(connections_dir.iterdir()):
                if not conn_path.is_dir():
                    continue

                name = conn_path.name
                has_schema = (conn_path / "schema" / "descriptions.yaml").exists()
                has_domain = (conn_path / "domain" / "model.md").exists()
                has_credentials = (conn_path / ".env").exists()
                has_state = (conn_path / "state.yaml").exists()

                # Detect connector type from connector.yaml
                connector_type = "sql"
                api_title = None
                base_url = None
                connector_yaml = conn_path / "connector.yaml"
                if connector_yaml.exists():
                    try:
                        import yaml as _yaml

                        with open(connector_yaml) as f:
                            cdata = _yaml.safe_load(f) or {}
                            connector_type = cdata.get("type", "sql")
                            # For API connectors, use api_title if available
                            if connector_type == "api":
                                api_title = cdata.get("api_title")
                                base_url = cdata.get("base_url", "")
                    except Exception:
                        pass

                # Try to detect dialect
                dialect = None
                if connector_type == "api":
                    # Use API title if available, derive from base_url, or use connection name
                    if api_title:
                        dialect = api_title
                    elif base_url:
                        # Extract domain name as display name (e.g., "api.dune.com" -> "Dune API")
                        try:
                            from urllib.parse import urlparse

                            parsed = urlparse(base_url)
                            domain = parsed.netloc or parsed.path
                            # Extract main domain part (e.g., "dune" from "api.dune.com")
                            parts = domain.replace("www.", "").split(".")
                            if len(parts) >= 2:
                                main_part = (
                                    parts[-2]
                                    if parts[-1] in ("com", "io", "ai", "co", "org", "net")
                                    else parts[0]
                                )  # noqa: E501
                            else:
                                main_part = parts[0]
                            dialect = f"{main_part.capitalize()} API"
                        except Exception:
                            dialect = f"{name} API"
                    else:
                        dialect = f"{name} API"
                elif connector_type == "file":
                    dialect = "duckdb"
                elif has_credentials:
                    env_file = conn_path / ".env"
                    try:
                        with open(env_file) as f:
                            for line in f:
                                if line.startswith("DATABASE_URL="):
                                    url = line.split("=", 1)[1].strip().strip("\"'")
                                    dialect = self._detect_dialect_from_url(url)
                                    break
                    except Exception:
                        pass

                # Get onboarding phase from state.yaml
                onboarding_phase = None
                if has_state:
                    try:
                        import yaml

                        with open(conn_path / "state.yaml") as f:
                            state = yaml.safe_load(f) or {}
                            onboarding_phase = state.get("phase")
                    except Exception:
                        pass

                connections.append(
                    {
                        "name": name,
                        "isActive": name == active_connection,
                        "hasSchema": has_schema,
                        "hasDomain": has_domain,
                        "hasCredentials": has_credentials,
                        "connectorType": connector_type,
                        "dialect": dialect,
                        "onboardingPhase": onboarding_phase,
                    }
                )

        return {
            "connections": connections,
            "activeConnection": active_connection,
        }

    async def _handle_connections_switch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Switch the active connection.

        Args:
            params: {"name": str} - The connection name to switch to

        Returns:
            {"success": bool, "activeConnection": str}
        """
        import yaml

        name = params.get("name")
        if not name:
            return {"success": False, "error": "Connection name required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        config_file = Path.home() / ".db-mcp" / "config.yaml"

        # Check if connection exists
        conn_path = connections_dir / name
        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' not found"}

        # Update config
        config = {}
        if config_file.exists():
            with open(config_file) as f:
                config = yaml.safe_load(f) or {}

        config["active_connection"] = name

        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        logger.info(f"Switched active connection to: {name}")

        return {
            "success": True,
            "activeConnection": name,
            "message": "Restart the UI server to use the new connection",
        }

    def _detect_dialect_from_url(self, url: str) -> str | None:
        """Detect database dialect from connection URL."""
        url_lower = url.lower()
        if url_lower.startswith("postgresql://") or url_lower.startswith("postgres://"):
            return "postgresql"
        elif url_lower.startswith("clickhouse"):
            return "clickhouse"
        elif url_lower.startswith("trino://"):
            return "trino"
        elif url_lower.startswith("mysql://"):
            return "mysql"
        elif url_lower.startswith("mssql://") or url_lower.startswith("sqlserver://"):
            return "mssql"
        elif url_lower.startswith("sqlite://"):
            return "sqlite"
        return None

    async def _handle_connections_create(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a new database connection.

        Args:
            params: {
                "name": str - Connection name (alphanumeric, dash, underscore)
                "connectorType": "sql" | "file" - Connector type (default: "sql")
                "databaseUrl": str - Database connection URL (for sql type)
                "directory": str - Directory path (for file type)
                "setActive": bool - Whether to set as active connection (default: True)
            }

        Returns:
            {"success": bool, "name": str, "dialect": str | None, "error": str | None}
        """
        import re

        name = params.get("name", "").strip()
        connector_type = params.get("connectorType", "sql")
        set_active = params.get("setActive", True)

        # Validate name
        if not name:
            return {"success": False, "error": "Connection name is required"}

        if not re.match(r"^[a-zA-Z0-9_-]+$", name):
            return {
                "success": False,
                "error": "Invalid name. Use only letters, numbers, dashes, underscores.",
            }

        connections_dir = Path.home() / ".db-mcp" / "connections"
        config_file = Path.home() / ".db-mcp" / "config.yaml"
        conn_path = connections_dir / name

        # Check if connection already exists
        if conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' already exists"}

        if connector_type == "api":
            return await self._create_api_connection(
                name, params, conn_path, config_file, set_active
            )

        if connector_type == "file":
            return await self._create_file_connection(
                name, params, conn_path, config_file, set_active
            )

        # --- SQL connection (existing behavior) ---
        database_url = params.get("databaseUrl", "").strip()

        # Validate database URL
        if not database_url:
            return {"success": False, "error": "Database URL is required"}

        # Detect dialect
        dialect = self._detect_dialect_from_url(database_url)

        # Test the connection before saving
        test_result = await self._test_database_url(database_url)
        if not test_result["success"]:
            return {
                "success": False,
                "error": f"Connection test failed: {test_result.get('error', 'Unknown error')}",
            }

        # Create connection directory
        conn_path.mkdir(parents=True, exist_ok=True)

        # Write .env file
        env_file = conn_path / ".env"
        with open(env_file, "w") as f:
            f.write("# db-mcp connection credentials\n")
            f.write("# This file is gitignored - do not commit\n\n")
            f.write(f'DATABASE_URL="{database_url}"\n')

        # Create .gitignore for the connection
        gitignore_file = conn_path / ".gitignore"
        with open(gitignore_file, "w") as f:
            f.write("# Ignore credentials\n")
            f.write(".env\n")
            f.write("# Ignore local state\n")
            f.write("state.yaml\n")

        # Set as active if requested
        if set_active:
            self._set_active_connection(name, config_file)

        logger.info(f"Created connection: {name} ({dialect})")

        return {
            "success": True,
            "name": name,
            "dialect": dialect,
            "isActive": set_active,
        }

    async def _create_file_connection(
        self,
        name: str,
        params: dict[str, Any],
        conn_path: Path,
        config_file: Path,
        set_active: bool,
    ) -> dict[str, Any]:
        """Create a file-type connection."""
        import yaml

        directory = params.get("directory", "").strip()
        if not directory:
            return {"success": False, "error": "Directory path is required"}

        # Test the directory
        test_result = self._test_file_directory(directory)
        if not test_result["success"]:
            return {
                "success": False,
                "error": f"Connection test failed: {test_result.get('error', 'Unknown error')}",
            }

        # Create connection directory
        conn_path.mkdir(parents=True, exist_ok=True)

        # Write connector.yaml
        connector_yaml = conn_path / "connector.yaml"
        with open(connector_yaml, "w") as f:
            yaml.dump(
                {"type": "file", "directory": directory},
                f,
                default_flow_style=False,
            )

        # Create .gitignore
        gitignore_file = conn_path / ".gitignore"
        with open(gitignore_file, "w") as f:
            f.write("# Ignore local state\n")
            f.write("state.yaml\n")

        # Set as active if requested
        if set_active:
            self._set_active_connection(name, config_file)

        logger.info(f"Created file connection: {name} (directory: {directory})")

        return {
            "success": True,
            "name": name,
            "dialect": "duckdb",
            "isActive": set_active,
        }

    async def _create_api_connection(
        self,
        name: str,
        params: dict[str, Any],
        conn_path: Path,
        config_file: Path,
        set_active: bool,
    ) -> dict[str, Any]:
        """Create an API-type connection."""
        import yaml

        base_url = params.get("baseUrl", "").strip()
        if not base_url:
            return {"success": False, "error": "Base URL is required"}

        auth_type = params.get("authType", "bearer")
        token_env = params.get("tokenEnv", "").strip()
        api_key = params.get("apiKey", "").strip()

        header_name = params.get("headerName", "").strip()

        # Build connector.yaml data
        auth_data: dict[str, Any] = {
            "type": auth_type,
            "token_env": token_env or "API_KEY",
        }
        if auth_type == "header" and header_name:
            auth_data["header_name"] = header_name

        connector_data: dict[str, Any] = {
            "type": "api",
            "base_url": base_url,
            "auth": auth_data,
            "endpoints": [],
            "pagination": {"type": "none"},
            "rate_limit": {"requests_per_second": 10.0},
        }

        # Create connection directory
        conn_path.mkdir(parents=True, exist_ok=True)

        # Write connector.yaml
        connector_yaml = conn_path / "connector.yaml"
        with open(connector_yaml, "w") as f:
            yaml.dump(connector_data, f, default_flow_style=False)

        # Write .env with API key if provided
        env_var_name = token_env or "API_KEY"
        env_file = conn_path / ".env"
        with open(env_file, "w") as f:
            f.write("# API connection credentials\n")
            f.write("# This file is gitignored - do not commit\n\n")
            if api_key:
                f.write(f"{env_var_name}={api_key}\n")
            else:
                f.write(f"# {env_var_name}=your_api_key_here\n")

        # Create data directory for JSONL files
        data_dir = conn_path / "data"
        data_dir.mkdir(exist_ok=True)

        # Create .gitignore
        gitignore_file = conn_path / ".gitignore"
        with open(gitignore_file, "w") as f:
            f.write("# Ignore credentials\n")
            f.write(".env\n")
            f.write("# Ignore local state\n")
            f.write("state.yaml\n")
            f.write("# Ignore synced data\n")
            f.write("data/\n")

        # Set as active if requested
        if set_active:
            self._set_active_connection(name, config_file)

        logger.info(f"Created API connection: {name} (base_url: {base_url})")

        return {
            "success": True,
            "name": name,
            "dialect": "duckdb",
            "isActive": set_active,
        }

    async def _handle_connections_sync(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sync data from API endpoints for a connection.

        Args:
            params: {
                "name": str - Connection name
                "endpoint": str | None - Specific endpoint to sync (optional)
            }

        Returns:
            {"success": bool, "synced": [...], "rows_fetched": {...}, "errors": [...]}
        """
        name = params.get("name")
        endpoint = params.get("endpoint")

        if not name:
            return {"success": False, "error": "Connection name is required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        conn_path = connections_dir / name

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' not found"}

        # Load connector config
        connector_yaml = conn_path / "connector.yaml"
        if not connector_yaml.exists():
            return {"success": False, "error": "No connector.yaml found"}

        try:
            from db_mcp.connectors import ConnectorConfig
            from db_mcp.connectors.api import APIConnector, APIConnectorConfig

            config = ConnectorConfig.from_yaml(connector_yaml)
            if not isinstance(config, APIConnectorConfig):
                return {"success": False, "error": "Connection is not an API connector"}

            data_dir = str(conn_path / "data")
            connector = APIConnector(config, data_dir)

            # Load .env for auth tokens
            env_file = conn_path / ".env"
            if env_file.exists():
                from dotenv import dotenv_values

                env_vars = dotenv_values(env_file)
                import os

                for k, v in env_vars.items():
                    if v is not None:
                        os.environ[k] = v

            result = connector.sync(endpoint_name=endpoint)

            return {
                "success": True,
                **result,
            }

        except Exception as e:
            logger.exception(f"API sync failed: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_connections_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        """Discover API endpoints for a connection.

        Uses OpenAPI spec parsing or endpoint probing to automatically
        find available endpoints and pagination config.

        Args:
            params: {
                "name": str - Connection name
            }

        Returns:
            {"success": bool, "strategy": str, "endpoints_found": int, ...}
        """
        name = params.get("name")

        if not name:
            return {"success": False, "error": "Connection name is required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        conn_path = connections_dir / name

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' not found"}

        connector_yaml = conn_path / "connector.yaml"
        if not connector_yaml.exists():
            return {"success": False, "error": "No connector.yaml found"}

        try:
            from db_mcp.connectors import ConnectorConfig
            from db_mcp.connectors.api import APIConnector, APIConnectorConfig

            config = ConnectorConfig.from_yaml(connector_yaml)
            if not isinstance(config, APIConnectorConfig):
                return {"success": False, "error": "Connection is not an API connector"}

            data_dir = str(conn_path / "data")
            env_path = str(conn_path / ".env")
            connector = APIConnector(config, data_dir, env_path=env_path)

            result = connector.discover()

            # Save updated config if endpoints were discovered
            if result.get("endpoints_found", 0) > 0:
                connector.save_connector_yaml(connector_yaml)

            return {
                "success": True,
                **result,
            }

        except Exception as e:
            logger.exception(f"API discovery failed: {e}")
            return {"success": False, "error": str(e)}

    def _set_active_connection(self, name: str, config_file: Path) -> None:
        """Set a connection as active in config.yaml."""
        import yaml

        config = {}
        if config_file.exists():
            with open(config_file) as f:
                config = yaml.safe_load(f) or {}

        config["active_connection"] = name

        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    async def _handle_connections_test(self, params: dict[str, Any]) -> dict[str, Any]:
        """Test a database connection.

        Args:
            params: {
                "name": str - Test existing connection by name, OR
                "databaseUrl": str - Test a database URL directly, OR
                "connectorType": "file", "directory": str - Test a file connection
            }

        Returns:
            {"success": bool, "message": str, "error": str | None, "dialect": str | None}
        """
        connector_type = params.get("connectorType", "sql")

        # API connector test
        if connector_type == "api":
            base_url = params.get("baseUrl", "").strip()
            if not base_url:
                return {"success": False, "error": "Base URL is required"}
            return await self._test_api_connection(params)

        # File connector test
        if connector_type == "file":
            directory = params.get("directory", "").strip()
            if not directory:
                return {"success": False, "error": "Directory path is required"}
            return self._test_file_directory(directory)

        # SQL connector test
        name = params.get("name")
        database_url = params.get("databaseUrl")

        if name:
            # Load URL from existing connection
            connections_dir = Path.home() / ".db-mcp" / "connections"
            conn_path = connections_dir / name
            env_file = conn_path / ".env"

            if not env_file.exists():
                return {"success": False, "error": f"Connection '{name}' not found"}

            # Parse .env file
            database_url = None
            with open(env_file) as f:
                for line in f:
                    if line.startswith("DATABASE_URL="):
                        database_url = line.split("=", 1)[1].strip().strip("\"'")
                        break

            if not database_url:
                return {"success": False, "error": "No DATABASE_URL in connection config"}

        elif database_url:
            pass  # Use provided URL
        else:
            return {"success": False, "error": "Either 'name' or 'databaseUrl' is required"}

        return await self._test_database_url(database_url)

    def _test_file_directory(self, directory: str) -> dict[str, Any]:
        """Test a file directory by checking for supported files."""
        from db_mcp.connectors.file import FileConnector, FileConnectorConfig

        config = FileConnectorConfig(directory=directory)
        connector = FileConnector(config)
        result = connector.test_connection()

        if result["connected"]:
            source_count = len(result.get("sources", {}))
            return {
                "success": True,
                "message": f"Found {source_count} table{'s' if source_count != 1 else ''}",
                "dialect": "duckdb",
                "sources": result.get("sources", {}),
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "No supported files found"),
                "dialect": "duckdb",
            }

    async def _test_api_connection(self, params: dict[str, Any]) -> dict[str, Any]:
        """Test an API connection by creating a temporary connector and testing it."""
        from db_mcp.connectors.api import APIAuthConfig, APIConnector, APIConnectorConfig

        base_url = params.get("baseUrl", "").strip()
        api_key = params.get("apiKey", "").strip()
        auth_type = params.get("authType", "bearer")
        header_name = params.get("headerName", "Authorization")
        token_env = params.get("tokenEnv", "API_KEY")

        # Build auth config
        auth = APIAuthConfig(
            type=auth_type,
            token_env=token_env,
            header_name=header_name,
        )

        # Build minimal API config
        config = APIConnectorConfig(
            base_url=base_url,
            auth=auth,
        )

        # Create temporary connector with in-memory data dir
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary .env file if API key provided
            env_path = None
            if api_key:
                import os

                env_path = os.path.join(temp_dir, ".env")
                with open(env_path, "w") as f:
                    f.write(f"{token_env}={api_key}\n")

            connector = APIConnector(config, temp_dir, env_path=env_path)
            result = connector.test_connection()

            if result["connected"]:
                endpoint_count = result.get("endpoints", 0)
                return {
                    "success": True,
                    "message": f"API reachable ({endpoint_count} endpoints configured)",
                    "dialect": result.get("dialect", "duckdb"),
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Connection failed"),
                    "dialect": result.get("dialect", "duckdb"),
                }

    async def _test_database_url(self, database_url: str) -> dict[str, Any]:
        """Test a database URL by attempting to connect.

        Uses get_engine() from db.connection which handles URL normalization
        (postgres:// → postgresql://) and dialect-specific config (Trino SSL).

        Returns:
            {"success": bool, "message": str, "dialect": str | None, "error": str | None}
        """
        from sqlalchemy import text

        from db_mcp.db.connection import get_engine

        dialect = self._detect_dialect_from_url(database_url)

        try:
            engine = get_engine(database_url)

            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            engine.dispose()

            return {
                "success": True,
                "message": "Connection successful",
                "dialect": dialect,
            }

        except Exception as e:
            error_msg = str(e)
            if database_url in error_msg:
                error_msg = error_msg.replace(database_url, "[DATABASE_URL]")

            # Suggest sslmode=require for PostgreSQL SSL errors
            hint = None
            if dialect == "postgresql" and "sslmode" not in database_url:
                ssl_keywords = ["ssl", "SSL", "certificate", "tls", "TLS", "HTTPS"]
                if any(kw in error_msg for kw in ssl_keywords):
                    hint = "Try adding ?sslmode=require to the database URL."

            logger.warning(f"Connection test failed: {error_msg}")

            return {
                "success": False,
                "error": error_msg,
                "hint": hint,
                "dialect": dialect,
            }

    async def _handle_connections_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete a database connection.

        Args:
            params: {"name": str} - Connection name to delete

        Returns:
            {"success": bool, "error": str | None}
        """
        import shutil

        import yaml

        name = params.get("name")
        if not name:
            return {"success": False, "error": "Connection name is required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        config_file = Path.home() / ".db-mcp" / "config.yaml"
        conn_path = connections_dir / name

        # Check if connection exists
        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' not found"}

        # Don't allow deleting the active connection without switching first
        active_connection = None
        if config_file.exists():
            with open(config_file) as f:
                config = yaml.safe_load(f) or {}
                active_connection = config.get("active_connection")

        if name == active_connection:
            # Find another connection to switch to
            other_connections = [
                d.name for d in connections_dir.iterdir() if d.is_dir() and d.name != name
            ]
            if other_connections:
                # Auto-switch to first available
                config["active_connection"] = other_connections[0]
                with open(config_file, "w") as f:
                    yaml.dump(config, f, default_flow_style=False)
                logger.info(f"Auto-switched to connection: {other_connections[0]}")
            else:
                # No other connections, clear active
                config.pop("active_connection", None)
                with open(config_file, "w") as f:
                    yaml.dump(config, f, default_flow_style=False)

        # Delete the connection directory
        shutil.rmtree(conn_path)

        logger.info(f"Deleted connection: {name}")

        return {"success": True, "name": name}

    async def _handle_connections_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get connection details.

        Args:
            params: {"name": str} - Connection name

        Returns:
            {"success": bool, "name": str, "connectorType": str,
             "databaseUrl": str (sql), "directory": str (file)}
        """
        import yaml
        from dotenv import dotenv_values

        name = params.get("name")
        if not name:
            return {"success": False, "error": "Connection name is required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        conn_path = connections_dir / name

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' not found"}

        # Detect connector type
        connector_yaml = conn_path / "connector.yaml"
        if connector_yaml.exists():
            with open(connector_yaml) as f:
                cdata = yaml.safe_load(f) or {}
            connector_type = cdata.get("type", "sql")
            if connector_type == "file":
                return {
                    "success": True,
                    "name": name,
                    "connectorType": "file",
                    "directory": cdata.get("directory", ""),
                }
            if connector_type == "api":
                auth = cdata.get("auth", {})
                endpoints = cdata.get("endpoints", [])
                pagination = cdata.get("pagination", {})
                rate_limit = cdata.get("rate_limit", {})
                return {
                    "success": True,
                    "name": name,
                    "connectorType": "api",
                    "baseUrl": cdata.get("base_url", ""),
                    "auth": {
                        "type": auth.get("type", "bearer"),
                        "tokenEnv": auth.get("token_env", ""),
                        "headerName": auth.get("header_name", "Authorization"),
                        "paramName": auth.get("param_name", "api_key"),
                    },
                    "endpoints": [
                        {
                            "name": ep.get("name", ""),
                            "path": ep.get("path", ""),
                            "method": ep.get("method", "GET"),
                        }
                        for ep in endpoints
                    ],
                    "pagination": {
                        "type": pagination.get("type", "none"),
                        "cursorParam": pagination.get("cursor_param", ""),
                        "cursorField": pagination.get("cursor_field", ""),
                        "pageSizeParam": pagination.get("page_size_param", "limit"),
                        "pageSize": pagination.get("page_size", 100),
                        "dataField": pagination.get("data_field", "data"),
                    },
                    "rateLimitRps": rate_limit.get("requests_per_second", 10.0),
                }

        # SQL connection
        env_file = conn_path / ".env"
        database_url = ""
        if env_file.exists():
            env_vars = dotenv_values(env_file)
            database_url = env_vars.get("DATABASE_URL", "")

        return {
            "success": True,
            "name": name,
            "connectorType": "sql",
            "databaseUrl": database_url,
        }

    async def _handle_connections_update(self, params: dict[str, Any]) -> dict[str, Any]:
        """Update a connection.

        Args:
            params: {"name": str, "databaseUrl": str} for SQL,
                    {"name": str, "directory": str} for file

        Returns:
            {"success": bool, "error": str | None}
        """
        import yaml

        name = params.get("name")
        if not name:
            return {"success": False, "error": "Connection name is required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        conn_path = connections_dir / name

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' not found"}

        # Detect connector type
        connector_yaml = conn_path / "connector.yaml"
        if connector_yaml.exists():
            with open(connector_yaml) as f:
                cdata = yaml.safe_load(f) or {}
            if cdata.get("type") == "file":
                directory = params.get("directory", "").strip()
                if not directory:
                    return {"success": False, "error": "Directory path is required"}
                cdata["directory"] = directory
                with open(connector_yaml, "w") as f:
                    yaml.dump(cdata, f, default_flow_style=False)
                logger.info(f"Updated file connection: {name}")
                return {"success": True, "name": name}

            if cdata.get("type") == "api":
                # Update API config fields
                if "baseUrl" in params:
                    cdata["base_url"] = params["baseUrl"]
                if "auth" in params:
                    auth = params["auth"]
                    cdata["auth"] = {
                        "type": auth.get("type", "bearer"),
                        "token_env": auth.get("tokenEnv", ""),
                        "header_name": auth.get("headerName", "Authorization"),
                        "param_name": auth.get("paramName", "api_key"),
                    }
                if "endpoints" in params:
                    cdata["endpoints"] = [
                        {
                            "name": ep.get("name", ""),
                            "path": ep.get("path", ""),
                            "method": ep.get("method", "GET"),
                        }
                        for ep in params["endpoints"]
                    ]
                if "pagination" in params:
                    pag = params["pagination"]
                    cdata["pagination"] = {
                        "type": pag.get("type", "none"),
                        "cursor_param": pag.get("cursorParam", ""),
                        "cursor_field": pag.get("cursorField", ""),
                        "page_size_param": pag.get("pageSizeParam", "limit"),
                        "page_size": pag.get("pageSize", 100),
                        "data_field": pag.get("dataField", "data"),
                    }
                if "rateLimitRps" in params:
                    cdata["rate_limit"] = {"requests_per_second": params["rateLimitRps"]}

                # Update API key in .env if provided
                api_key = params.get("apiKey", "").strip()
                if api_key:
                    token_env = cdata.get("auth", {}).get("token_env", "API_KEY")
                    env_file = conn_path / ".env"
                    with open(env_file, "w") as f:
                        f.write(f"{token_env}={api_key}\n")

                with open(connector_yaml, "w") as f:
                    yaml.dump(cdata, f, default_flow_style=False)
                logger.info(f"Updated API connection: {name}")
                return {"success": True, "name": name}

        # SQL connection
        database_url = params.get("databaseUrl")
        if not database_url:
            return {"success": False, "error": "Database URL is required"}

        env_file = conn_path / ".env"
        with open(env_file, "w") as f:
            f.write(f"DATABASE_URL={database_url}\n")

        logger.info(f"Updated connection: {name}")

        return {"success": True, "name": name}

    # ========== Context Viewer Methods ==========

    # Folder importance levels for the UI
    # critical: Must be populated for basic functionality
    # recommended: Improves quality significantly
    # optional: Nice to have, not required
    _FOLDER_IMPORTANCE: dict[str, str] = {
        "schema": "critical",
        "domain": "critical",
        "examples": "recommended",
        "instructions": "recommended",
        "metrics": "recommended",
        "learnings": "optional",
        "traces": "optional",
    }

    # Folders to always show (even if they don't exist on disk)
    # These are the core semantic layer folders
    _EXPECTED_FOLDERS: list[str] = [
        "schema",
        "domain",
        "examples",
        "instructions",
        "metrics",
    ]

    # Stock README content for empty directories
    _STOCK_READMES: dict[str, str] = {
        "schema": """# Schema Descriptions

This directory contains schema descriptions for your database tables and columns.

**Why is this important?**

Schema descriptions are essential for SQL generation. Without them, the AI cannot
understand your database structure and will be unable to generate accurate queries.

## Files

- `descriptions.yaml` - Table and column descriptions used for SQL generation

## How to populate

1. **Recommended**: Run the onboarding process via Claude Desktop or the MCP tools
2. Or manually create `descriptions.yaml` with table/column descriptions

## Format

```yaml
tables:
  - name: users
    full_name: public.users
    description: "User accounts and profiles"
    columns:
      - name: id
        description: "Primary key"
      - name: email
        description: "User email address (unique)"
```

## Getting Started

Ask Claude to help you onboard your database:
> "Let's set up the schema descriptions for my database"
""",
        "domain": """# Domain Model

This directory contains the semantic domain model for your database.

**Why is this important?**

The domain model provides business context that helps the AI understand how your
data relates to real-world concepts, resulting in more accurate and relevant queries.

## Files

- `model.md` - Natural language description of your data domain

## Purpose

The domain model helps the AI understand:
- Business concepts and terminology
- Relationships between entities
- Common query patterns and use cases
- Industry-specific language and metrics

## How to populate

1. **Recommended**: Complete the schema onboarding first, then ask Claude to
   generate the domain model
2. Or manually write a description of your data domain

## Getting Started

After completing schema descriptions, ask Claude:
> "Generate a domain model for my database based on the schema descriptions"
""",
        "examples": """# Query Examples

This directory contains query examples that improve SQL generation accuracy.

**Why is this important?**

Query examples teach the AI your specific query patterns and preferences. The more
examples you provide, the better the AI becomes at generating queries that match your
needs.

## Files

Each example is stored as a separate YAML file with natural language and SQL mapping.

## Format

```yaml
natural_language: "Show me all active users"
sql: "SELECT * FROM users WHERE status = 'active'"
tags: ["users", "status"]
notes: "Filter by status column"
```

## How to add examples

1. **Easiest**: After a successful query, provide feedback to save it as an example
2. Or manually create YAML files in this directory

## Getting Started

Start using the database with natural language queries. After each successful query,
you can save it as an example to improve future results.
""",
        "instructions": """# Business Rules & Instructions

This directory contains business rules and special instructions for SQL generation.

**Why is this important?**

Business rules ensure that generated queries follow your organization's conventions,
data access policies, and best practices. They provide guardrails and context that
improve query quality.

## Files

- `business_rules.yaml` - List of rules and instructions

## Format

```yaml
rules:
  - "Always use UTC timestamps"
  - "Filter deleted records with is_deleted = false"
  - "Use INNER JOIN for customer tables"
  - "Limit results to 1000 rows by default"
```

## Examples of Business Rules

- Data access restrictions (e.g., "Only query data from the last 90 days")
- Naming conventions (e.g., "Date columns end with _at or _date")
- Performance guidelines (e.g., "Always include partition key in WHERE clause")
- Business logic (e.g., "Active users are those with last_login in past 30 days")

## Getting Started

Think about the rules and conventions your team follows when writing queries,
and document them here.
""",
        "metrics": """# Business Metrics

This directory contains standardized metric definitions for your organization.

**Why is this important?**

Metric definitions ensure consistent calculation of KPIs across all queries. Instead
of re-defining "Monthly Active Users" each time, you define it once and reference it
consistently.

## Files

- `catalog.yaml` - Metric definitions catalog

## Format

```yaml
metrics:
  - name: monthly_active_users
    display_name: "Monthly Active Users"
    description: "Users who logged in at least once in the past 30 days"
    sql: "COUNT(DISTINCT user_id) FILTER (WHERE last_login >= CURRENT_DATE - 30)"
    tables: ["users"]
    tags: ["engagement", "core-kpi"]
```

## Common Metric Types

- **Engagement**: DAU, WAU, MAU, session duration
- **Revenue**: MRR, ARR, ARPU, LTV
- **Growth**: Signups, activations, churn rate
- **Operations**: Response time, error rate, uptime

## Getting Started

Start by defining your organization's most important KPIs - the metrics that appear
in executive dashboards and reports.
""",
        "learnings": """# Learnings

This directory contains patterns and insights learned from your query history.

**Why is this important?**

Learnings capture institutional knowledge about your data - schema quirks, common
pitfalls, and best practices discovered through usage. This helps the AI avoid
known issues and follow proven patterns.

## Files

- `patterns.md` - Common query patterns and techniques
- `schema_gotchas.md` - Schema-specific quirks and workarounds

## What to document

- **Schema quirks**: "The `status` column uses 0/1 instead of boolean"
- **Naming conventions**: "Date columns use `_at` suffix, not `_date`"
- **Performance tips**: "Always filter by `tenant_id` first for faster queries"
- **Data quality issues**: "Some `email` values are null for legacy accounts"
- **Business logic**: "Revenue calculations should exclude refunded orders"

## Getting Started

As you work with your database, document any insights or gotchas you discover.
This knowledge helps the AI generate better queries over time.
""",
    }

    def _get_connections_dir(self) -> Path:
        """Get the connections directory path."""
        return Path.home() / ".db-mcp" / "connections"

    def _is_git_enabled(self, conn_path: Path) -> bool:
        """Check if git is enabled for a connection directory."""
        return (conn_path / ".git").exists()

    def _git_commit(self, conn_path: Path, message: str, files: list[str]) -> bool:
        """Commit changes to git if enabled.

        Returns True if commit was made, False otherwise.
        """
        if not self._is_git_enabled(conn_path):
            return False

        from db_mcp.git_utils import git

        try:
            git.add(conn_path, files)
            result = git.commit(conn_path, message)

            if result:
                logger.info(f"Git commit: {message}")
                return True
            else:
                logger.debug("Nothing to commit")
                return False

        except Exception as e:
            logger.warning(f"Git commit failed: {e}")
            return False

    async def _handle_context_tree(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get the file tree for all connections.

        Args:
            params: {} - No parameters required

        Returns:
            {
                "connections": [
                    {
                        "name": str,
                        "isActive": bool,
                        "gitEnabled": bool,
                        "folders": [
                            {
                                "name": str,  # "schema", "domain", "training"
                                "path": str,  # Relative path
                                "files": [
                                    {"name": str, "path": str, "size": int}
                                ]
                            }
                        ]
                    }
                ]
            }
        """
        import yaml as yaml_lib

        connections_dir = self._get_connections_dir()
        config_file = Path.home() / ".db-mcp" / "config.yaml"

        # Get active connection
        active_connection = None
        if config_file.exists():
            with open(config_file) as f:
                config = yaml_lib.safe_load(f) or {}
                active_connection = config.get("active_connection")

        # Allowed file extensions
        allowed_extensions = {".yaml", ".yml", ".md"}

        # Hidden/system items to skip
        hidden_prefixes = (".", "_")
        skip_files = {"state.yaml"}  # Internal state files

        connections = []
        if connections_dir.exists():
            for conn_path in sorted(connections_dir.iterdir()):
                if not conn_path.is_dir():
                    continue

                name = conn_path.name
                git_enabled = self._is_git_enabled(conn_path)

                folders = []
                root_files = []

                # Scan all items in the connection directory
                for item_path in sorted(conn_path.iterdir()):
                    item_name = item_path.name

                    # Skip hidden files/folders and system files
                    if item_name.startswith(hidden_prefixes):
                        continue
                    if item_name in skip_files:
                        continue

                    if item_path.is_dir():
                        # It's a folder - scan for files
                        files = []
                        for file_path in sorted(item_path.iterdir()):
                            if not file_path.is_file():
                                continue
                            if file_path.name.startswith(hidden_prefixes):
                                continue
                            if file_path.suffix.lower() not in allowed_extensions:
                                continue

                            files.append(
                                {
                                    "name": file_path.name,
                                    "path": f"{item_name}/{file_path.name}",
                                    "size": file_path.stat().st_size,
                                }
                            )

                        # Get importance level for this folder
                        importance = self._FOLDER_IMPORTANCE.get(item_name)
                        has_readme = item_name in self._STOCK_READMES

                        folders.append(
                            {
                                "name": item_name,
                                "path": item_name,
                                "files": files,
                                "isEmpty": len(files) == 0,
                                "importance": importance,
                                "hasReadme": has_readme,
                            }
                        )

                    elif item_path.is_file():
                        # It's a root-level file
                        if item_path.suffix.lower() not in allowed_extensions:
                            continue

                        root_files.append(
                            {
                                "name": item_name,
                                "path": item_name,
                                "size": item_path.stat().st_size,
                            }
                        )

                # Create expected folders that don't exist on disk
                existing_folder_names = {f["name"] for f in folders}
                for expected_folder in self._EXPECTED_FOLDERS:
                    if expected_folder not in existing_folder_names:
                        # Create the folder
                        folder_path = conn_path / expected_folder
                        folder_path.mkdir(exist_ok=True)

                        importance = self._FOLDER_IMPORTANCE.get(expected_folder)
                        has_readme = expected_folder in self._STOCK_READMES
                        folders.append(
                            {
                                "name": expected_folder,
                                "path": expected_folder,
                                "files": [],
                                "isEmpty": True,
                                "importance": importance,
                                "hasReadme": has_readme,
                            }
                        )

                # Sort folders by name for consistent ordering
                folders.sort(key=lambda f: f["name"])

                connections.append(
                    {
                        "name": name,
                        "isActive": name == active_connection,
                        "gitEnabled": git_enabled,
                        "folders": folders,
                        "rootFiles": root_files,
                    }
                )

        return {"connections": connections}

    async def _handle_context_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Read a file's content.

        Args:
            params: {
                "connection": str - Connection name
                "path": str - Relative path within connection (e.g., "schema/descriptions.yaml")
            }

        Returns:
            {"success": bool, "content": str, "error": str | None}
        """
        connection = params.get("connection")
        path = params.get("path")

        if not connection or not path:
            return {"success": False, "error": "connection and path are required"}

        # Validate path (prevent directory traversal)
        if ".." in path or path.startswith("/"):
            return {"success": False, "error": "Invalid path"}

        connections_dir = self._get_connections_dir()
        file_path = connections_dir / connection / path

        # Check if this is a folder path (requesting stock README)
        if file_path.is_dir():
            folder_name = path.split("/")[0] if "/" in path else path
            if folder_name in self._STOCK_READMES:
                return {
                    "success": True,
                    "content": self._STOCK_READMES[folder_name],
                    "isStockReadme": True,
                }
            return {"success": False, "error": "Folder has no setup guide"}

        # Check file exists
        if not file_path.exists():
            # Check if this is a request for a stock README (folder doesn't exist)
            parts = path.split("/")
            if len(parts) == 1 and parts[0] in self._STOCK_READMES:
                # Return stock README for empty folder
                return {
                    "success": True,
                    "content": self._STOCK_READMES[parts[0]],
                    "isStockReadme": True,
                }
            return {"success": False, "error": f"File not found: {path}"}

        # Validate extension
        allowed_extensions = {".yaml", ".yml", ".md"}
        if file_path.suffix.lower() not in allowed_extensions:
            return {"success": False, "error": "File type not allowed"}

        try:
            content = file_path.read_text(encoding="utf-8")
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_context_write(self, params: dict[str, Any]) -> dict[str, Any]:
        """Write content to a file.

        Args:
            params: {
                "connection": str - Connection name
                "path": str - Relative path within connection
                "content": str - File content to write
            }

        Returns:
            {"success": bool, "gitCommit": bool, "error": str | None}
        """
        connection = params.get("connection")
        path = params.get("path")
        content = params.get("content")

        if not connection or not path:
            return {"success": False, "error": "connection and path are required"}
        if content is None:
            return {"success": False, "error": "content is required"}

        # Validate path
        if ".." in path or path.startswith("/"):
            return {"success": False, "error": "Invalid path"}

        # Validate extension
        allowed_extensions = {".yaml", ".yml", ".md"}
        if not any(path.endswith(ext) for ext in allowed_extensions):
            return {"success": False, "error": "File type not allowed"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        file_path = conn_path / path

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            file_path.write_text(content, encoding="utf-8")

            # Git commit if enabled
            git_commit = self._git_commit(conn_path, f"Update {path}", [path])

            logger.info(f"Wrote file: {connection}/{path}")

            return {"success": True, "gitCommit": git_commit}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_context_create(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a new file.

        Args:
            params: {
                "connection": str - Connection name
                "path": str - Relative path for new file
                "content": str - Initial content (optional, defaults to empty)
            }

        Returns:
            {"success": bool, "gitCommit": bool, "error": str | None}
        """
        connection = params.get("connection")
        path = params.get("path")
        content = params.get("content", "")

        if not connection or not path:
            return {"success": False, "error": "connection and path are required"}

        # Validate path
        if ".." in path or path.startswith("/"):
            return {"success": False, "error": "Invalid path"}

        # Validate extension
        allowed_extensions = {".yaml", ".yml", ".md"}
        if not any(path.endswith(ext) for ext in allowed_extensions):
            return {"success": False, "error": "File type not allowed. Use .yaml, .yml, or .md"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        file_path = conn_path / path

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        if file_path.exists():
            return {"success": False, "error": f"File already exists: {path}"}

        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            file_path.write_text(content, encoding="utf-8")

            # Git commit if enabled
            git_commit = self._git_commit(conn_path, f"Create {path}", [path])

            logger.info(f"Created file: {connection}/{path}")

            return {"success": True, "gitCommit": git_commit}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_context_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete a file (moves to .trash or git rm).

        Args:
            params: {
                "connection": str - Connection name
                "path": str - Relative path to delete
            }

        Returns:
            {"success": bool, "gitCommit": bool, "trashedTo": str | None, "error": str | None}
        """
        import shutil

        connection = params.get("connection")
        path = params.get("path")

        if not connection or not path:
            return {"success": False, "error": "connection and path are required"}

        # Validate path
        if ".." in path or path.startswith("/"):
            return {"success": False, "error": "Invalid path"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        file_path = conn_path / path

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}

        try:
            git_enabled = self._is_git_enabled(conn_path)

            if git_enabled:
                # Use git rm (file is recoverable via git history)
                from db_mcp.git_utils import git

                git.rm(conn_path, path)
                git.commit(conn_path, f"Delete {path}")

                logger.info(f"Git rm: {connection}/{path}")
                return {"success": True, "gitCommit": True}

            else:
                # Move to .trash directory
                trash_dir = conn_path / ".trash"
                trash_dir.mkdir(exist_ok=True)

                # Generate unique trash name if needed
                trash_path = trash_dir / file_path.name
                counter = 1
                while trash_path.exists():
                    stem = file_path.stem
                    suffix = file_path.suffix
                    trash_path = trash_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                shutil.move(str(file_path), str(trash_path))

                logger.info(f"Trashed: {connection}/{path} -> .trash/{trash_path.name}")
                return {
                    "success": True,
                    "gitCommit": False,
                    "trashedTo": f".trash/{trash_path.name}",
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_context_add_rule(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add a business rule to the connection's rules file.

        Properly parses YAML and appends to the rules list.
        Optionally resolves a knowledge gap by ID.

        Args:
            params: {
                "connection": str - Connection name
                "rule": str - The rule text to add
                "gapId": str | None - Optional gap ID to resolve
            }
        """
        import yaml

        connection = params.get("connection")
        rule = params.get("rule")
        gap_id = params.get("gapId")

        if not connection or not rule:
            return {
                "success": False,
                "error": "connection and rule are required",
            }

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        if not conn_path.exists():
            return {
                "success": False,
                "error": f"Connection '{connection}' not found",
            }

        rules_path = conn_path / "instructions" / "business_rules.yaml"

        try:
            if rules_path.exists():
                with open(rules_path) as f:
                    data = yaml.safe_load(f) or {}
            else:
                rules_path.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "version": "1.0.0",
                    "provider_id": connection,
                    "rules": [],
                }

            rules = data.get("rules", [])
            if not isinstance(rules, list):
                rules = []

            # Skip if rule already exists
            if rule in rules:
                return {"success": True, "duplicate": True}

            rules.append(rule)
            data["rules"] = rules

            with open(rules_path, "w") as f:
                yaml.dump(
                    data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )

            # Git commit if enabled
            rel_path = "instructions/business_rules.yaml"
            self._git_commit(conn_path, "Add business rule", [rel_path])

            # Resolve gap if ID provided
            if gap_id:
                try:
                    from db_mcp.gaps.store import resolve_gap

                    resolve_gap(connection, gap_id, "business_rules")
                except Exception as e:
                    logger.warning(f"Failed to resolve gap {gap_id}: {e}")

            logger.info(f"Added business rule to {connection}: {rule[:60]}")
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_context_usage(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get context file usage statistics from traces.

        Args:
            params: {
                "connection": str - Connection name
                "days": int (default 7) - Number of days to analyze
            }

        Returns:
            {
                "files": {
                    "examples/foo.yaml": {"count": 12, "lastUsed": 1707800000}
                },
                "folders": {
                    "examples": {"count": 45, "lastUsed": 1707800000}
                }
            }
        """
        from collections import defaultdict
        from db_mcp.bicp.traces import extract_context_paths, list_trace_dates, read_traces_from_jsonl

        connection = params.get("connection")
        days = params.get("days", 7)

        if not connection:
            return {"success": False, "error": "connection is required"}

        # Get the connection path
        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        # For now, use a fixed user_id - in the future this could be parameterized
        user_id = "default"
        
        # Get trace dates within the time window
        import time
        cutoff_time = time.time() - (days * 86400)  # days ago
        
        available_dates = list_trace_dates(conn_path, user_id)
        
        file_counts = defaultdict(int)
        file_last_used = {}
        
        # Process traces from each date
        for date_str in available_dates:
            # Parse date to check if within window
            try:
                from datetime import datetime
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                if date_obj.timestamp() < cutoff_time:
                    continue
            except ValueError:
                continue
                
            trace_file = conn_path / "traces" / user_id / f"{date_str}.jsonl"
            if not trace_file.exists():
                continue
                
            traces = read_traces_from_jsonl(trace_file)
            
            for trace in traces:
                for span in trace.get("spans", []):
                    attrs = span.get("attributes", {})
                    span_timestamp = span.get("start_time", 0)
                    
                    # Source 1: Shell commands (grep/cat/find/ls)
                    tool_name = attrs.get("tool.name")
                    command = attrs.get("command")
                    if tool_name == "shell" and command:
                        context_paths = extract_context_paths(command)
                        for path in context_paths:
                            # Map search terms to likely files in context directories
                            for context_dir in ["schema", "examples", "instructions", "domain", "data", "learnings"]:
                                file_key = f"{context_dir}/{path}"
                                file_counts[file_key] += 1
                                file_last_used[file_key] = max(file_last_used.get(file_key, 0), span_timestamp)
                    
                    # Source 2: Knowledge file loads (from generation.py instrumentation)
                    files_used = attrs.get("knowledge.files_used")
                    if files_used:
                        for file_path in files_used:
                            file_counts[file_path] += 1
                            file_last_used[file_path] = max(file_last_used.get(file_path, 0), span_timestamp)
                    
                    # Source 3: Resource reads (MCP resources/read)
                    if span.get("name") == "resources/read":
                        resource_uri = attrs.get("resource.uri")
                        if resource_uri and resource_uri.startswith("file://"):
                            # Extract relative path
                            import urllib.parse
                            file_path = urllib.parse.unquote(resource_uri.replace("file://", ""))
                            # Only track context-related paths
                            for context_dir in ["schema", "examples", "instructions", "domain", "data", "learnings"]:
                                if context_dir in file_path:
                                    # Extract relative path from context directory
                                    parts = file_path.split(context_dir, 1)
                                    if len(parts) > 1:
                                        rel_path = f"{context_dir}{parts[1]}"
                                        file_counts[rel_path] += 1
                                        file_last_used[rel_path] = max(file_last_used.get(rel_path, 0), span_timestamp)
        
        # Aggregate folder counts
        folder_counts = defaultdict(int)
        folder_last_used = {}
        
        for file_path, count in file_counts.items():
            if "/" in file_path:
                folder = file_path.split("/")[0]
                folder_counts[folder] += count
                folder_last_used[folder] = max(folder_last_used.get(folder, 0), file_last_used.get(file_path, 0))
        
        return {
            "files": {
                path: {"count": count, "lastUsed": int(file_last_used.get(path, 0))}
                for path, count in file_counts.items()
            },
            "folders": {
                path: {"count": count, "lastUsed": int(folder_last_used.get(path, 0))}
                for path, count in folder_counts.items()
            }
        }

    # ========== Knowledge Gaps Methods ==========

    async def _handle_gaps_dismiss(self, params: dict[str, Any]) -> dict[str, Any]:
        """Dismiss a knowledge gap as a false positive.

        Args:
            params: {
                "connection": str - Connection name
                "gapId": str - Gap ID to dismiss
                "reason": str | None - Optional reason for dismissal
            }
        """
        connection = params.get("connection")
        gap_id = params.get("gapId")
        reason = params.get("reason")

        if not connection or not gap_id:
            return {
                "success": False,
                "error": "connection and gapId are required",
            }

        try:
            from db_mcp.gaps.store import dismiss_gap

            result = dismiss_gap(connection, gap_id, reason)

            if result.get("dismissed"):
                logger.info(
                    f"Dismissed gap {gap_id} in {connection}" + (f": {reason}" if reason else "")
                )
                return {
                    "success": True,
                    "count": result["count"],
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Failed to dismiss gap"),
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_insights_save_example(self, params: dict[str, Any]) -> dict[str, Any]:
        """Save a repeated query as a training example.

        Args:
            params: {
                "connection": str - Connection name
                "sql": str - The SQL query to save
                "intent": str - Natural language description
            }
        """
        connection = params.get("connection")
        sql = params.get("sql")
        intent = params.get("intent")

        if not connection or not sql or not intent:
            return {
                "success": False,
                "error": "connection, sql, and intent are required",
            }

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        if not conn_path.exists():
            return {
                "success": False,
                "error": f"Connection '{connection}' not found",
            }

        try:
            from db_mcp.training.store import add_example

            result = add_example(
                provider_id=connection,
                natural_language=intent,
                sql=sql,
            )

            if result.get("added"):
                # Git commit if enabled
                file_path = result.get("file_path")
                if file_path:
                    self._git_commit(
                        conn_path,
                        "Add training example from insights",
                        [file_path],
                    )

                return {
                    "success": True,
                    "example_id": result["example_id"],
                    "total_examples": result["total_examples"],
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Failed to save example"),
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== Git History Methods ==========

    async def _handle_git_history(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get commit history for a file.

        Args:
            params: {
                "connection": str - Connection name
                "path": str - Relative path within connection
                "limit": int - Maximum number of commits to return (default: 50)
            }

        Returns:
            {
                "success": bool,
                "commits": [
                    {
                        "hash": str,      # Short commit hash
                        "fullHash": str,  # Full commit hash
                        "message": str,   # Commit message
                        "date": str,      # ISO 8601 date
                        "author": str,    # Author name
                    }
                ],
                "error": str | None
            }
        """
        from db_mcp.git_utils import git

        connection = params.get("connection")
        path = params.get("path")
        limit = params.get("limit", 50)

        if not connection or not path:
            return {"success": False, "error": "connection and path are required"}

        # Validate path
        if ".." in path or path.startswith("/"):
            return {"success": False, "error": "Invalid path"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        if not self._is_git_enabled(conn_path):
            return {"success": False, "error": "Git is not enabled for this connection"}

        file_path = conn_path / path
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}

        try:
            commits_list = git.log(conn_path, path, limit=limit)

            commits = [
                {
                    "hash": c.hash,
                    "fullHash": c.full_hash,
                    "message": c.message,
                    "date": c.date.isoformat(),
                    "author": c.author,
                }
                for c in commits_list
            ]

            return {"success": True, "commits": commits}

        except Exception as e:
            return {"success": False, "error": f"Git error: {e}"}

    async def _handle_git_show(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get file content at a specific commit.

        Args:
            params: {
                "connection": str - Connection name
                "path": str - Relative path within connection
                "commit": str - Commit hash (short or full)
            }

        Returns:
            {
                "success": bool,
                "content": str,    # File content at that commit
                "commit": str,     # The commit hash used
                "error": str | None
            }
        """
        from db_mcp.git_utils import git

        connection = params.get("connection")
        path = params.get("path")
        commit = params.get("commit")

        if not connection or not path or not commit:
            return {"success": False, "error": "connection, path, and commit are required"}

        # Validate path
        if ".." in path or path.startswith("/"):
            return {"success": False, "error": "Invalid path"}

        # Validate commit hash (alphanumeric only)
        if not commit.replace("-", "").isalnum():
            return {"success": False, "error": "Invalid commit hash"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        if not self._is_git_enabled(conn_path):
            return {"success": False, "error": "Git is not enabled for this connection"}

        try:
            content = git.show(conn_path, path, commit)

            return {
                "success": True,
                "content": content,
                "commit": commit,
            }

        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Git error: {e}"}

    async def _handle_git_revert(self, params: dict[str, Any]) -> dict[str, Any]:
        """Revert a file to its content at a specific commit.

        Args:
            params: {
                "connection": str - Connection name
                "path": str - Relative path within connection
                "commit": str - Commit hash to revert to
            }

        Returns:
            {
                "success": bool,
                "message": str | None,
                "error": str | None
            }
        """
        from db_mcp.git_utils import git

        connection = params.get("connection")
        path = params.get("path")
        commit = params.get("commit")

        if not connection or not path or not commit:
            return {"success": False, "error": "connection, path, and commit are required"}

        # Validate path
        if ".." in path or path.startswith("/"):
            return {"success": False, "error": "Invalid path"}

        # Validate commit hash (alphanumeric only)
        if not commit.replace("-", "").isalnum():
            return {"success": False, "error": "Invalid commit hash"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        if not self._is_git_enabled(conn_path):
            return {"success": False, "error": "Git is not enabled for this connection"}

        try:
            # Get file content at the specified commit
            content = git.show(conn_path, path, commit)

            # Write the content back to the file
            file_path = conn_path / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

            # Commit the revert
            self._git_commit(
                conn_path,
                f"Revert {path} to {commit[:7]}",
                [path],
            )

            return {
                "success": True,
                "message": f"Reverted {path} to commit {commit[:7]}",
            }

        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Git revert error: {e}"}

    # ========== Trace Viewer Methods ==========

    def _get_active_connection_path(self) -> Path | None:
        """Get the active connection path from config.yaml.

        The UI server doesn't set CONNECTION_NAME, so we read
        active_connection directly from the config file.
        """
        import yaml

        config_file = Path.home() / ".db-mcp" / "config.yaml"
        if not config_file.exists():
            return None

        with open(config_file) as f:
            config = yaml.safe_load(f) or {}

        active = config.get("active_connection")
        if not active:
            return None

        return Path.home() / ".db-mcp" / "connections" / active

    async def _handle_traces_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """List traces from live collector or historical JSONL files.

        Args:
            params: {
                "source": "live" | "historical" - Where to read traces from
                "date": str | None - YYYY-MM-DD date for historical (default: today)
                "limit": int - Max traces to return (default: 50)
            }

        Returns:
            {"success": bool, "traces": [...], "source": str}
        """
        source = params.get("source", "live")
        limit = params.get("limit", 50)

        if source == "live":
            from db_mcp.console.collector import get_collector

            traces = get_collector().get_traces(limit=limit)
            return {"success": True, "traces": traces, "source": "live"}

        elif source == "historical":
            from datetime import datetime

            from db_mcp.bicp.traces import read_traces_from_jsonl
            from db_mcp.traces import get_traces_dir, get_user_id_from_config, is_traces_enabled

            if not is_traces_enabled():
                return {
                    "success": False,
                    "traces": [],
                    "source": "historical",
                    "error": "Traces are not enabled",
                }

            user_id = get_user_id_from_config()
            if not user_id:
                return {
                    "success": False,
                    "traces": [],
                    "source": "historical",
                    "error": "No user_id configured",
                }

            connection_path = self._get_active_connection_path()
            if not connection_path:
                return {
                    "success": False,
                    "traces": [],
                    "source": "historical",
                    "error": "No active connection",
                }

            date_str = params.get("date") or datetime.now().strftime("%Y-%m-%d")
            traces_dir = get_traces_dir(connection_path, user_id)
            file_path = traces_dir / f"{date_str}.jsonl"

            traces = read_traces_from_jsonl(file_path, limit=limit)
            return {"success": True, "traces": traces, "source": "historical"}

        return {"success": False, "traces": [], "error": f"Unknown source: {source}"}

    async def _handle_traces_clear(self, params: dict[str, Any]) -> dict[str, Any]:
        """Clear the live span collector.

        Returns:
            {"success": bool}
        """
        from db_mcp.console.collector import get_collector

        get_collector().clear()
        return {"success": True}

    async def _handle_traces_dates(self, params: dict[str, Any]) -> dict[str, Any]:
        """List available historical trace dates.

        Returns:
            {"success": bool, "enabled": bool, "dates": [str]}
        """
        from db_mcp.bicp.traces import list_trace_dates
        from db_mcp.traces import get_user_id_from_config, is_traces_enabled

        enabled = is_traces_enabled()
        if not enabled:
            return {"success": True, "enabled": False, "dates": []}

        user_id = get_user_id_from_config()
        if not user_id:
            return {"success": True, "enabled": True, "dates": []}

        connection_path = self._get_active_connection_path()
        if not connection_path:
            return {"success": True, "enabled": True, "dates": []}

        dates = list_trace_dates(connection_path, user_id)

        return {"success": True, "enabled": True, "dates": dates}

    # ========== Insights Methods ==========

    async def _handle_insights_analyze(self, params: dict[str, Any]) -> dict[str, Any]:
        """Analyze traces for semantic layer gaps and inefficiencies.

        Aggregates live + historical traces and runs analysis to surface:
        - Tool usage distribution
        - Errors and validation failures
        - Repeated queries (AI struggling)
        - Knowledge capture activity
        - Semantic layer completeness

        Args:
            params: {
                "days": int - Number of historical days to include (default: 7)
            }

        Returns:
            {"success": bool, "analysis": {...}, "error": str | None}
        """
        from datetime import datetime, timedelta

        from db_mcp.bicp.traces import analyze_traces, read_traces_from_jsonl
        from db_mcp.console.collector import get_collector

        days = params.get("days", 7)

        # Collect all traces: live + historical
        all_traces: list[dict] = []

        # Live traces
        try:
            live = get_collector().get_traces(limit=500)
            all_traces.extend(live)
        except Exception as e:
            logger.warning(f"Failed to get live traces: {e}")

        # Historical traces
        connection_path = self._get_active_connection_path()
        if connection_path:
            try:
                from db_mcp.traces import (
                    get_traces_dir,
                    get_user_id_from_config,
                    is_traces_enabled,
                )

                if is_traces_enabled():
                    user_id = get_user_id_from_config()
                    if user_id:
                        traces_dir = get_traces_dir(connection_path, user_id)
                        today = datetime.now()
                        for i in range(days):
                            date = today - timedelta(days=i)
                            date_str = date.strftime("%Y-%m-%d")
                            file_path = traces_dir / f"{date_str}.jsonl"
                            if file_path.exists():
                                day_traces = read_traces_from_jsonl(file_path, limit=500)
                                all_traces.extend(day_traces)
            except Exception as e:
                logger.warning(f"Failed to read historical traces: {e}")

        # Deduplicate by trace_id (live may overlap with today's JSONL)
        seen_ids: set[str] = set()
        unique_traces: list[dict] = []
        for t in all_traces:
            tid = t.get("trace_id", "")
            if tid not in seen_ids:
                seen_ids.add(tid)
                unique_traces.append(t)

        analysis = analyze_traces(unique_traces, connection_path, days=days)

        # Detect and store proactive insights from trace analysis
        if connection_path:
            try:
                from db_mcp.insights.detector import scan_and_update

                scan_and_update(connection_path, analysis)
            except Exception as e:
                logger.warning(f"Insight detection failed: {e}")

        # Auto-resolve gaps whose terms now appear in business rules
        if connection_path:
            try:
                from db_mcp.gaps.store import auto_resolve_gaps

                provider_id = connection_path.name
                resolved = auto_resolve_gaps(provider_id)
                if resolved > 0:
                    # Re-read gaps, rebuilding groups by group_id
                    from db_mcp.gaps.store import load_gaps_from_path

                    all_gaps = load_gaps_from_path(connection_path)
                    groups: dict[str, list] = {}
                    ungrouped: list = []
                    for gap in all_gaps.gaps:
                        if gap.group_id:
                            groups.setdefault(gap.group_id, []).append(gap)
                        else:
                            ungrouped.append(gap)

                    def _gap_to_entry(gap_list: list) -> dict:
                        terms = []
                        all_cols: list[str] = []
                        suggested = None
                        earliest = float("inf")
                        st = "resolved"
                        src = gap_list[0].source.value if gap_list else "traces"
                        for g in gap_list:
                            terms.append(
                                {
                                    "term": g.term,
                                    "searchCount": 0,
                                    "session": "",
                                    "timestamp": (g.detected_at.timestamp()),
                                }
                            )
                            all_cols.extend(g.related_columns)
                            if g.suggested_rule:
                                suggested = g.suggested_rule
                            earliest = min(
                                earliest,
                                g.detected_at.timestamp(),
                            )
                            if g.status.value == "open":
                                st = "open"
                            src = g.source.value
                        seen: set[str] = set()
                        unique: list[str] = []
                        for c in all_cols:
                            if c not in seen:
                                seen.add(c)
                                unique.append(c)
                        return {
                            "id": gap_list[0].id,
                            "terms": terms,
                            "totalSearches": 0,
                            "timestamp": earliest,
                            "schemaMatches": [
                                {
                                    "name": c.split(".")[-1],
                                    "table": c,
                                    "type": "column",
                                }
                                for c in unique[:10]
                            ],
                            "suggestedRule": suggested,
                            "status": st,
                            "source": src,
                        }

                    persisted_gaps = []
                    for gl in groups.values():
                        persisted_gaps.append(_gap_to_entry(gl))
                    for gap in ungrouped:
                        persisted_gaps.append(_gap_to_entry([gap]))
                    analysis["vocabularyGaps"] = persisted_gaps
                    logger.info(f"Auto-resolved {resolved} knowledge gaps on insights refresh")
            except Exception as e:
                logger.warning(f"Failed to auto-resolve knowledge gaps: {e}")

        return {"success": True, "analysis": analysis}

    # ========== Metrics & Dimensions Methods ==========

    async def _handle_metrics_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """List approved metrics and dimensions for a connection.

        Args:
            params: {"connection": str}
        """
        connection = params.get("connection")
        if not connection:
            return {"success": False, "error": "connection is required"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        from db_mcp.metrics.store import load_dimensions, load_metrics

        metrics_catalog = load_metrics(connection)
        dimensions_catalog = load_dimensions(connection)

        approved_metrics = metrics_catalog.approved()
        approved_dimensions = dimensions_catalog.approved()

        return {
            "success": True,
            "metrics": [m.model_dump(mode="json") for m in approved_metrics],
            "dimensions": [d.model_dump(mode="json") for d in approved_dimensions],
            "metricCount": len(approved_metrics),
            "dimensionCount": len(approved_dimensions),
        }

    async def _handle_metrics_add(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add a metric or dimension to the approved catalog.

        Args:
            params: {
                "connection": str,
                "type": "metric" | "dimension",
                "data": dict  - metric or dimension fields
            }
        """
        connection = params.get("connection")
        item_type = params.get("type", "metric")
        data = params.get("data", {})

        if not connection:
            return {"success": False, "error": "connection is required"}
        if not data or not data.get("name"):
            return {"success": False, "error": "data with name is required"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        try:
            if item_type == "dimension":
                from db_mcp.metrics.store import add_dimension

                result = add_dimension(
                    provider_id=connection,
                    name=data["name"],
                    column=data.get("column", ""),
                    description=data.get("description", ""),
                    display_name=data.get("display_name"),
                    dim_type=data.get("type", "categorical"),
                    tables=data.get("tables", []),
                    values=data.get("values", []),
                    synonyms=data.get("synonyms", []),
                    status=data.get("status", "approved"),
                )

                if result.get("added"):
                    file_path = result.get("file_path", "")
                    rel = "metrics/dimensions.yaml"
                    self._git_commit(conn_path, f"Add dimension: {data['name']}", [rel])
                    return {
                        "success": True,
                        "name": data["name"],
                        "type": "dimension",
                        "filePath": file_path,
                    }
                return {"success": False, "error": result.get("error", "Failed to add")}
            else:
                from db_mcp.metrics.store import add_metric

                result = add_metric(
                    provider_id=connection,
                    name=data["name"],
                    description=data.get("description", ""),
                    sql=data.get("sql", ""),
                    display_name=data.get("display_name"),
                    tables=data.get("tables", []),
                    parameters=data.get("parameters", []),
                    tags=data.get("tags", []),
                    dimensions=data.get("dimensions", []),
                    notes=data.get("notes"),
                    status=data.get("status", "approved"),
                )

                if result.get("added"):
                    file_path = result.get("file_path", "")
                    rel = "metrics/catalog.yaml"
                    self._git_commit(conn_path, f"Add metric: {data['name']}", [rel])
                    return {
                        "success": True,
                        "name": data["name"],
                        "type": "metric",
                        "filePath": file_path,
                    }
                return {"success": False, "error": result.get("error", "Failed to add")}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_metrics_update(self, params: dict[str, Any]) -> dict[str, Any]:
        """Update an existing metric or dimension.

        Deletes the old entry and re-adds with updated data.

        Args:
            params: {
                "connection": str,
                "type": "metric" | "dimension",
                "name": str,
                "data": dict
            }
        """
        connection = params.get("connection")
        item_type = params.get("type", "metric")
        name = params.get("name")
        data = params.get("data", {})

        if not connection or not name:
            return {"success": False, "error": "connection and name are required"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        try:
            if item_type == "dimension":
                from db_mcp.metrics.store import add_dimension, delete_dimension

                delete_dimension(connection, name)
                new_name = data.get("name", name)
                result = add_dimension(
                    provider_id=connection,
                    name=new_name,
                    column=data.get("column", ""),
                    description=data.get("description", ""),
                    display_name=data.get("display_name"),
                    dim_type=data.get("type", "categorical"),
                    tables=data.get("tables", []),
                    values=data.get("values", []),
                    synonyms=data.get("synonyms", []),
                )
                if result.get("added"):
                    rel = "metrics/dimensions.yaml"
                    self._git_commit(conn_path, f"Update dimension: {new_name}", [rel])
                    return {"success": True, "name": new_name, "type": "dimension"}
                return {"success": False, "error": result.get("error", "Failed to update")}
            else:
                from db_mcp.metrics.store import add_metric, delete_metric

                delete_metric(connection, name)
                new_name = data.get("name", name)
                result = add_metric(
                    provider_id=connection,
                    name=new_name,
                    description=data.get("description", ""),
                    sql=data.get("sql", ""),
                    display_name=data.get("display_name"),
                    tables=data.get("tables", []),
                    parameters=data.get("parameters", []),
                    tags=data.get("tags", []),
                    dimensions=data.get("dimensions", []),
                    notes=data.get("notes"),
                    status=data.get("status", "approved"),
                )
                if result.get("added"):
                    rel = "metrics/catalog.yaml"
                    self._git_commit(conn_path, f"Update metric: {new_name}", [rel])
                    return {"success": True, "name": new_name, "type": "metric"}
                return {"success": False, "error": result.get("error", "Failed to update")}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_metrics_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete a metric or dimension from the catalog.

        Args:
            params: {
                "connection": str,
                "type": "metric" | "dimension",
                "name": str
            }
        """
        connection = params.get("connection")
        item_type = params.get("type", "metric")
        name = params.get("name")

        if not connection or not name:
            return {"success": False, "error": "connection and name are required"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        try:
            if item_type == "dimension":
                from db_mcp.metrics.store import delete_dimension

                result = delete_dimension(connection, name)
                if result.get("deleted"):
                    rel = "metrics/dimensions.yaml"
                    self._git_commit(conn_path, f"Delete dimension: {name}", [rel])
                    return {"success": True, "name": name, "type": "dimension"}
                return {"success": False, "error": result.get("error", "Not found")}
            else:
                from db_mcp.metrics.store import delete_metric

                result = delete_metric(connection, name)
                if result.get("deleted"):
                    rel = "metrics/catalog.yaml"
                    self._git_commit(conn_path, f"Delete metric: {name}", [rel])
                    return {"success": True, "name": name, "type": "metric"}
                return {"success": False, "error": result.get("error", "Not found")}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_metrics_candidates(self, params: dict[str, Any]) -> dict[str, Any]:
        """Mine the vault for metric and dimension candidates.

        Args:
            params: {"connection": str}
        """
        connection = params.get("connection")
        if not connection:
            return {"success": False, "error": "connection is required"}

        connections_dir = self._get_connections_dir()
        conn_path = connections_dir / connection
        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{connection}' not found"}

        try:
            from db_mcp.metrics.mining import mine_metrics_and_dimensions
            from db_mcp.metrics.store import load_dimensions, load_metrics

            result = await mine_metrics_and_dimensions(conn_path)

            mined_metric_names = {c.metric.name for c in result.get("metric_candidates", [])}
            mined_dim_names = {c.dimension.name for c in result.get("dimension_candidates", [])}

            metric_candidates_out = [
                {
                    "metric": c.metric.model_dump(mode="json"),
                    "confidence": c.confidence,
                    "source": c.source,
                    "evidence": c.evidence,
                }
                for c in result.get("metric_candidates", [])
            ]
            dimension_candidates_out = [
                {
                    "dimension": c.dimension.model_dump(mode="json"),
                    "confidence": c.confidence,
                    "source": c.source,
                    "evidence": c.evidence,
                    "category": c.category,
                }
                for c in result.get("dimension_candidates", [])
            ]

            # Include persisted candidates (status=candidate in catalog)
            # that weren't already found by mining
            metrics_catalog = load_metrics(connection)
            for m in metrics_catalog.candidates():
                if m.name not in mined_metric_names:
                    metric_candidates_out.append(
                        {
                            "metric": m.model_dump(mode="json"),
                            "confidence": 0.6,
                            "source": "catalog",
                            "evidence": [],
                        }
                    )

            dimensions_catalog = load_dimensions(connection)
            for d in dimensions_catalog.candidates():
                if d.name not in mined_dim_names:
                    dimension_candidates_out.append(
                        {
                            "dimension": d.model_dump(mode="json"),
                            "confidence": 0.6,
                            "source": "catalog",
                            "evidence": [],
                            "category": "Other",
                        }
                    )

            return {
                "success": True,
                "metricCandidates": metric_candidates_out,
                "dimensionCandidates": dimension_candidates_out,
            }

        except Exception as e:
            logger.exception(f"Mining failed: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_metrics_approve(self, params: dict[str, Any]) -> dict[str, Any]:
        """Approve a mined candidate into the catalog.

        Args:
            params: {
                "connection": str,
                "type": "metric" | "dimension",
                "data": dict  - the candidate's metric/dimension data (possibly edited)
            }
        """
        # Approving sets status to "approved" so it moves from
        # the Candidates tab to the Catalog tab
        params_copy = dict(params)
        data = params_copy.get("data", {})
        data["created_by"] = "approved"
        data["status"] = "approved"
        params_copy["data"] = data
        return await self._handle_metrics_add(params_copy)

    # ========== Schema Explorer Methods ==========

    async def _handle_schema_catalogs(self, params: dict[str, Any]) -> dict[str, Any]:
        """List available catalogs in the database.

        Args:
            params: {} - No parameters required

        Returns:
            {
                "success": bool,
                "catalogs": [str],  # List of catalog names
                "error": str | None
            }
        """
        try:
            connector = get_connector()
            catalogs = connector.get_catalogs()
            return {"success": True, "catalogs": catalogs}
        except Exception as e:
            logger.exception(f"Failed to list catalogs: {e}")
            return {"success": False, "catalogs": [], "error": str(e)}

    async def _handle_schema_schemas(self, params: dict[str, Any]) -> dict[str, Any]:
        """List schemas in a catalog.

        Args:
            params: {
                "catalog": str | None - Catalog to list schemas for (optional)
            }

        Returns:
            {
                "success": bool,
                "schemas": [{"name": str, "catalog": str, "tableCount": int | None}],
                "error": str | None
            }
        """
        catalog = params.get("catalog")

        try:
            connector = get_connector()
            schemas_list = []
            schema_names = connector.get_schemas(catalog=catalog)

            for name in schema_names:
                if name:
                    # Try to get table count
                    table_count = None
                    try:
                        tables = connector.get_tables(schema=name, catalog=catalog)
                        table_count = len(tables)
                    except Exception:
                        pass

                    schemas_list.append(
                        {
                            "name": name,
                            "catalog": catalog,
                            "tableCount": table_count,
                        }
                    )

            return {"success": True, "schemas": schemas_list}
        except Exception as e:
            logger.exception(f"Failed to list schemas: {e}")
            return {"success": False, "schemas": [], "error": str(e)}

    async def _handle_schema_tables(self, params: dict[str, Any]) -> dict[str, Any]:
        """List tables in a schema.

        Args:
            params: {
                "schema": str - Schema name (required)
                "catalog": str | None - Catalog name (optional)
            }

        Returns:
            {
                "success": bool,
                "tables": [{"name": str, "description": str | None}],
                "error": str | None
            }
        """
        schema = params.get("schema")
        catalog = params.get("catalog")

        if not schema:
            return {"success": False, "tables": [], "error": "schema is required"}

        try:
            connector = get_connector()
            tables = connector.get_tables(schema=schema, catalog=catalog)

            # Load schema descriptions if available
            provider_id = self._settings.provider_id
            schema_desc = load_schema_descriptions(provider_id)
            desc_by_name: dict[str, str | None] = {}
            if schema_desc:
                for t in schema_desc.tables:
                    desc_by_name[t.full_name or t.name] = t.description
                    desc_by_name[t.name] = t.description

            tables_list = []
            for table in tables:
                name = table.get("name", table) if isinstance(table, dict) else table
                full_name = table.get("full_name", name) if isinstance(table, dict) else name
                description = desc_by_name.get(full_name) or desc_by_name.get(name)

                tables_list.append(
                    {
                        "name": name,
                        "description": description,
                    }
                )

            return {"success": True, "tables": tables_list}
        except Exception as e:
            logger.exception(f"Failed to list tables: {e}")
            return {"success": False, "tables": [], "error": str(e)}

    async def _handle_schema_columns(self, params: dict[str, Any]) -> dict[str, Any]:
        """List columns in a table.

        Args:
            params: {
                "table": str - Table name (required)
                "schema": str | None - Schema name (optional)
                "catalog": str | None - Catalog name (optional)
            }

        Returns:
            {
                "success": bool,
                "columns": [{
                    "name": str,
                    "type": str,
                    "nullable": bool,
                    "description": str | None,
                    "isPrimaryKey": bool
                }],
                "error": str | None
            }
        """
        table = params.get("table")
        schema = params.get("schema")
        catalog = params.get("catalog")

        if not table:
            return {"success": False, "columns": [], "error": "table is required"}

        try:
            connector = get_connector()
            columns = connector.get_columns(table, schema=schema, catalog=catalog)

            # Load schema descriptions if available
            provider_id = self._settings.provider_id
            schema_desc = load_schema_descriptions(provider_id)
            col_descs: dict[str, str | None] = {}
            if schema_desc:
                for t in schema_desc.tables:
                    if t.name == table or t.full_name == table:
                        for col in t.columns or []:
                            col_descs[col.name] = col.description
                        break

            columns_list = []
            for col in columns:
                columns_list.append(
                    {
                        "name": col["name"],
                        "type": col.get("type", "VARCHAR"),
                        "nullable": col.get("nullable", True),
                        "description": col_descs.get(col["name"]),
                        "isPrimaryKey": col.get("primary_key", False),
                    }
                )

            return {"success": True, "columns": columns_list}
        except Exception as e:
            logger.exception(f"Failed to list columns: {e}")
            return {"success": False, "columns": [], "error": str(e)}

    async def _handle_schema_validate_link(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate a semantic link (db://catalog/schema/table[/column]).

        Args:
            params: {
                "link": str - The db:// link to validate
            }

        Returns:
            {
                "success": bool,
                "valid": bool,
                "parsed": {
                    "catalog": str | None,
                    "schema": str | None,
                    "table": str | None,
                    "column": str | None
                },
                "error": str | None
            }
        """
        link = params.get("link", "")

        # Parse db://catalog/schema/table[/column]
        if not link.startswith("db://"):
            return {
                "success": True,
                "valid": False,
                "parsed": {},
                "error": "Link must start with db://",
            }

        parts = link[5:].split("/")  # Remove 'db://' prefix
        if len(parts) < 3:
            return {
                "success": True,
                "valid": False,
                "parsed": {},
                "error": "Link must have at least catalog/schema/table",
            }

        catalog = parts[0] if parts[0] else None
        schema = parts[1] if len(parts) > 1 else None
        table = parts[2] if len(parts) > 2 else None
        column = parts[3] if len(parts) > 3 else None

        parsed = {
            "catalog": catalog,
            "schema": schema,
            "table": table,
            "column": column,
        }

        try:
            connector = get_connector()
            # Validate table exists
            if table and schema:
                tables = connector.get_tables(schema=schema, catalog=catalog)
                table_names = [t.get("name", t) if isinstance(t, dict) else t for t in tables]
                if table not in table_names:
                    return {
                        "success": True,
                        "valid": False,
                        "parsed": parsed,
                        "error": f"Table '{table}' not found in {catalog}/{schema}",
                    }

                # Validate column if specified
                if column:
                    columns = connector.get_columns(table, schema=schema, catalog=catalog)
                    column_names = [c["name"] for c in columns]
                    if column not in column_names:
                        return {
                            "success": True,
                            "valid": False,
                            "parsed": parsed,
                            "error": f"Column '{column}' not found in {table}",
                        }

            return {"success": True, "valid": True, "parsed": parsed}

        except Exception as e:
            return {
                "success": True,
                "valid": False,
                "parsed": parsed,
                "error": str(e),
            }

    # =========================================================================
    # Agent configuration handlers
    # =========================================================================

    async def _handle_agents_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """List detected MCP agents and their db-mcp configuration status."""
        from db_mcp.agents import AGENTS, load_agent_config

        agents_list = []
        for agent_id, agent in AGENTS.items():
            installed = bool(agent.detect_fn and agent.detect_fn())
            config_exists = agent.config_path.exists()

            dbmcp_configured = False
            binary_path = None
            if config_exists:
                config = load_agent_config(agent)
                mcp_section = config.get(agent.config_key, {})
                if "db-mcp" in mcp_section:
                    dbmcp_configured = True
                    binary_path = mcp_section["db-mcp"].get("command")

            agents_list.append(
                {
                    "id": agent_id,
                    "name": agent.name,
                    "installed": installed,
                    "configPath": str(agent.config_path),
                    "configExists": config_exists,
                    "configFormat": agent.config_format,
                    "dbmcpConfigured": dbmcp_configured,
                    "binaryPath": binary_path,
                }
            )

        return {"agents": agents_list}

    async def _handle_agents_configure(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add db-mcp to an agent's MCP config."""
        from db_mcp.agents import (
            AGENTS,
            configure_agent_for_dbmcp,
            get_db_mcp_binary_path,
        )

        agent_id = params.get("agentId", "")
        if agent_id not in AGENTS:
            return {"success": False, "error": f"Unknown agent: {agent_id}"}

        binary_path = get_db_mcp_binary_path()
        try:
            result = configure_agent_for_dbmcp(agent_id, binary_path)
            if result:
                return {
                    "success": True,
                    "configPath": str(AGENTS[agent_id].config_path),
                }
            return {"success": False, "error": "Configuration failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_agents_remove(self, params: dict[str, Any]) -> dict[str, Any]:
        """Remove db-mcp from an agent's MCP config."""
        from db_mcp.agents import AGENTS, remove_dbmcp_from_agent

        agent_id = params.get("agentId", "")
        if agent_id not in AGENTS:
            return {"success": False, "error": f"Unknown agent: {agent_id}"}

        try:
            result = remove_dbmcp_from_agent(agent_id)
            if result:
                return {"success": True}
            return {"success": False, "error": "Removal failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_agents_config_snippet(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return the MCP servers config snippet for an agent."""
        import json as _json

        from db_mcp.agents import AGENTS, _dict_to_toml, load_agent_config

        agent_id = params.get("agentId", "")
        if agent_id not in AGENTS:
            return {"success": False, "error": f"Unknown agent: {agent_id}"}

        agent = AGENTS[agent_id]
        config = load_agent_config(agent)
        mcp_section = config.get(agent.config_key, {})

        if not mcp_section:
            return {
                "success": True,
                "snippet": "",
                "format": agent.config_format,
                "configKey": agent.config_key,
            }

        if agent.config_format == "json":
            snippet = _json.dumps(mcp_section, indent=2)
        else:
            snippet = _dict_to_toml(mcp_section)

        return {
            "success": True,
            "snippet": snippet,
            "format": agent.config_format,
            "configKey": agent.config_key,
        }

    async def _handle_agents_config_write(self, params: dict[str, Any]) -> dict[str, Any]:
        """Write an edited MCP servers config snippet back to an agent's config file.

        Validates the snippet (JSON/TOML parse + type check) before writing.
        Only replaces the MCP servers section; other config keys are preserved.
        """
        import json as _json
        import tomllib

        from db_mcp.agents import (
            AGENTS,
            _dict_to_toml,
            load_agent_config,
        )

        agent_id = params.get("agentId", "")
        snippet = params.get("snippet", "")

        if agent_id not in AGENTS:
            return {"success": False, "error": f"Unknown agent: {agent_id}"}

        if not snippet or not snippet.strip():
            return {"success": False, "error": "Snippet cannot be empty"}

        agent = AGENTS[agent_id]

        # Parse and validate the snippet
        if agent.config_format == "json":
            try:
                parsed = _json.loads(snippet)
            except _json.JSONDecodeError as e:
                return {"success": False, "error": f"Invalid JSON: {e}"}
            if not isinstance(parsed, dict):
                return {"success": False, "error": "Snippet must be a JSON object"}
        else:
            try:
                parsed = tomllib.loads(snippet)
            except tomllib.TOMLDecodeError as e:
                return {"success": False, "error": f"Invalid TOML: {e}"}

        # Load full config, replace just the MCP section, save
        config = load_agent_config(agent)
        config[agent.config_key] = parsed

        agent.config_path.parent.mkdir(parents=True, exist_ok=True)
        if agent.config_format == "json":
            with open(agent.config_path, "w") as f:
                _json.dump(config, f, indent=2)
        else:
            with open(agent.config_path, "w") as f:
                f.write(_dict_to_toml(config))

        return {"success": True}
