"""BICP Agent implementation for db-mcp.

This module provides a BICP (Business Intelligence Client Protocol) agent
that integrates with db-mcp's existing infrastructure for SQL generation,
validation, and execution.

Custom UI methods (connections, context, traces, insights, metrics, schema,
agents, playground) are served via the REST API router in db_mcp.api.router.
This agent handles only the 5 BICP protocol methods:
  - generate_candidates
  - execute_query
  - list_schemas
  - describe_schema
  - semantic_search
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

import db_mcp.services.connection as connection_service
import db_mcp.services.context as context_service
import db_mcp.services.query as query_service
import db_mcp.services.schema as schema_service
from db_mcp.config import get_settings
from db_mcp.services.connection import get_active_connection_path

logger = logging.getLogger(__name__)


class DBMCPAgent(BICPAgent):
    """BICP Agent backed by db-mcp infrastructure.

    This agent implements the BICP protocol using db-mcp's existing
    components for database introspection, SQL generation, validation,
    and execution.

    Custom UI methods (connections, context, traces, etc.) are handled
    by the REST API router — see db_mcp.api.router.

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

    def _detect_dialect(self) -> str:
        """Detect the database dialect from configuration."""
        try:
            _, connection_path = self._resolve_connection_context()
            return connection_service.get_connection_dialect(connection_path=connection_path)
        except Exception:
            return "unknown"

    def _resolve_connection_context(self) -> tuple[str, Path]:
        """Resolve the connection context used by BICP methods.

        Priority:
        1. Active connection from ~/.db-mcp/config.yaml (UI-managed)
        2. Process settings effective connection
        """
        active_path = get_active_connection_path(
            config_file=Path.home() / ".db-mcp" / "config.yaml",
            connections_dir=Path.home() / ".db-mcp" / "connections",
        )
        if active_path is not None:
            return active_path.name, active_path

        settings = getattr(self, "_settings", None) or get_settings()
        return settings.get_effective_provider_id(), settings.get_effective_connection_path()

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
        provider_id, conn_path = self._resolve_connection_context()
        intent = query.natural_language

        # Load schema context
        schema, examples = context_service.load_semantic_context(
            provider_id, connection_path=conn_path
        )
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
            analysis = query_service.analyze_candidate_sql(
                candidate_sql,
                connection_path=conn_path,
            )
            warnings = analysis["warnings"]
            raw_cost = analysis["cost"]
            if isinstance(raw_cost, QueryCost):
                cost = raw_cost
            elif isinstance(raw_cost, dict):
                cost = QueryCost(
                    estimated_rows=raw_cost.get("estimated_rows"),
                    cost_units=raw_cost.get("cost_units"),
                )

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

        start_time = time.time()

        try:
            _, conn_path = self._resolve_connection_context()
            columns, rows = query_service.execute_bicp_query(
                sql,
                connection_path=conn_path,
            )

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
            _, conn_path = self._resolve_connection_context()
            catalog = params.catalog
            schema_result = schema_service.list_schemas_with_counts(conn_path, catalog=catalog)
            schemas_list = [
                SchemaInfo(
                    catalog=schema["catalog"],
                    schema_=schema["name"],
                    table_count=schema.get("tableCount"),
                )
                for schema in schema_result["schemas"]
            ]

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
            provider_id, conn_path = self._resolve_connection_context()
            tables_result = schema_service.list_tables(
                conn_path,
                schema=schema_name,
                catalog=catalog,
            )
            tables = tables_result["tables"]

            # Load schema descriptions if available
            schema_desc = context_service.load_schema_knowledge(
                provider_id, connection_path=conn_path
            )
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
                        col_result = schema_service.describe_table(
                            table_name=table["name"],
                            connection_path=conn_path,
                            schema=schema_name,
                            catalog=catalog,
                        )
                        for col in col_result["columns"]:
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

        provider_id, conn_path = self._resolve_connection_context()
        results: list[SemanticSearchMatch] = []
        schema, examples = context_service.load_semantic_context(
            provider_id, connection_path=conn_path
        )

        # Search tables and columns
        if SemanticObjectType.TABLE in object_types or SemanticObjectType.COLUMN in object_types:
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
