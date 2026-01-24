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
from db_mcp.db.connection import get_engine
from db_mcp.db.introspection import get_catalogs, get_columns, get_schemas, get_tables
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

    def _detect_dialect(self) -> str:
        """Detect the database dialect from configuration."""
        try:
            engine = get_engine()
            return engine.dialect.name
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
            engine = get_engine()

            with engine.connect() as conn:
                result = conn.execute(text(sql))
                column_names = list(result.keys())

                # Build column metadata
                columns = []
                for name in column_names:
                    columns.append({"name": name, "dataType": "VARCHAR"})

                # Fetch rows (with reasonable limit)
                rows = []
                for i, row in enumerate(result):
                    if i >= 10000:  # Safety limit
                        break
                    rows.append(list(row))

            # Update query execution time
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
            catalog = params.catalog
            schemas_list = []

            if catalog:
                # List schemas in specific catalog
                schema_names = get_schemas(catalog=catalog)
                for name in schema_names:
                    if name:
                        # Get table count for this schema
                        try:
                            tables = get_tables(schema=name, catalog=catalog)
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
                catalogs = get_catalogs()
                for cat in catalogs:
                    schema_names = get_schemas(catalog=cat)
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
            # Get tables from database
            tables = get_tables(schema=schema_name, catalog=catalog)

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
                        col_data = get_columns(
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

                # Try to detect dialect from .env
                dialect = None
                if has_credentials:
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
                "databaseUrl": str - Database connection URL
                "setActive": bool - Whether to set as active connection (default: True)
            }

        Returns:
            {"success": bool, "name": str, "dialect": str | None, "error": str | None}
        """
        import re

        import yaml

        name = params.get("name", "").strip()
        database_url = params.get("databaseUrl", "").strip()
        set_active = params.get("setActive", True)

        # Validate name
        if not name:
            return {"success": False, "error": "Connection name is required"}

        if not re.match(r"^[a-zA-Z0-9_-]+$", name):
            return {
                "success": False,
                "error": "Invalid name. Use only letters, numbers, dashes, underscores.",
            }

        # Validate database URL
        if not database_url:
            return {"success": False, "error": "Database URL is required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        config_file = Path.home() / ".db-mcp" / "config.yaml"
        conn_path = connections_dir / name

        # Check if connection already exists
        if conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' already exists"}

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
            config = {}
            if config_file.exists():
                with open(config_file) as f:
                    config = yaml.safe_load(f) or {}

            config["active_connection"] = name

            config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, "w") as f:
                yaml.dump(config, f, default_flow_style=False)

        logger.info(f"Created connection: {name} ({dialect})")

        return {
            "success": True,
            "name": name,
            "dialect": dialect,
            "isActive": set_active,
        }

    async def _handle_connections_test(self, params: dict[str, Any]) -> dict[str, Any]:
        """Test a database connection.

        Args:
            params: {
                "name": str - Test existing connection by name, OR
                "databaseUrl": str - Test a database URL directly
            }

        Returns:
            {"success": bool, "message": str, "error": str | None, "dialect": str | None}
        """
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

    async def _test_database_url(self, database_url: str) -> dict[str, Any]:
        """Test a database URL by attempting to connect.

        Returns:
            {"success": bool, "message": str, "dialect": str | None, "error": str | None}
        """
        from sqlalchemy import create_engine, text

        dialect = self._detect_dialect_from_url(database_url)

        try:
            # Create engine with short timeout
            engine = create_engine(
                database_url,
                connect_args={"connect_timeout": 10} if dialect == "postgresql" else {},
            )

            # Try to connect and run simple query
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
            # Clean up sensitive info from error message
            if database_url in error_msg:
                error_msg = error_msg.replace(database_url, "[DATABASE_URL]")

            logger.warning(f"Connection test failed: {error_msg}")

            return {
                "success": False,
                "error": error_msg,
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
        """Get connection details including database URL.

        Args:
            params: {"name": str} - Connection name

        Returns:
            {"success": bool, "name": str, "databaseUrl": str, "error": str | None}
        """
        from dotenv import dotenv_values

        name = params.get("name")
        if not name:
            return {"success": False, "error": "Connection name is required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        conn_path = connections_dir / name
        env_file = conn_path / ".env"

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' not found"}

        # Load database URL from .env file
        database_url = ""
        if env_file.exists():
            env_vars = dotenv_values(env_file)
            database_url = env_vars.get("DATABASE_URL", "")

        return {
            "success": True,
            "name": name,
            "databaseUrl": database_url,
        }

    async def _handle_connections_update(self, params: dict[str, Any]) -> dict[str, Any]:
        """Update a connection's database URL.

        Args:
            params: {"name": str, "databaseUrl": str} - Connection name and new URL

        Returns:
            {"success": bool, "error": str | None}
        """
        name = params.get("name")
        database_url = params.get("databaseUrl")

        if not name:
            return {"success": False, "error": "Connection name is required"}
        if not database_url:
            return {"success": False, "error": "Database URL is required"}

        connections_dir = Path.home() / ".db-mcp" / "connections"
        conn_path = connections_dir / name
        env_file = conn_path / ".env"

        if not conn_path.exists():
            return {"success": False, "error": f"Connection '{name}' not found"}

        # Update the .env file
        with open(env_file, "w") as f:
            f.write(f"DATABASE_URL={database_url}\n")

        logger.info(f"Updated connection: {name}")

        return {"success": True, "name": name}
