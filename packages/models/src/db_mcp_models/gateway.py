"""Gateway request, response, and lifecycle types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SQLQuery:
    """A SQL query to be executed against a SQL or SQL-like connector."""

    sql: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EndpointQuery:
    """An API endpoint query (REST/GraphQL style connector)."""

    endpoint: str
    params: dict[str, Any] = field(default_factory=dict)
    method: str = "GET"
    max_pages: int = 1


@dataclass(frozen=True)
class DataRequest:
    """Caller intent — what to run and against which connection.

    Immutable value object. Not persisted. Passed to gateway.create()
    which validates it and returns a ValidatedQuery with a stable query_id.
    """

    connection: str
    query: SQLQuery | EndpointQuery


@dataclass(frozen=True)
class RunOptions:
    """Per-execution overrides. Keeps ValidatedQuery immutable.

    Passed to gateway.execute() to control how a validated query is run
    this time, without mutating the query definition itself.
    """

    confirmed: bool = False
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class ColumnMeta:
    """Typed column descriptor returned by adapter introspect and execute calls."""

    name: str
    type: str | None = None


@dataclass(frozen=True)
class ValidatedQuery:
    """Persisted, immutable record of a validated DataRequest.

    Created by gateway.create(). Has a stable query_id that survives
    restarts and can be executed multiple times via gateway.execute().
    Never mutated after creation.
    """

    query_id: str
    connection: str
    query_type: str              # "sql" | "endpoint"
    request: DataRequest
    cost_tier: str               # "low" | "confirm" | "reject" | "unknown"
    validated_at: datetime
    sql: str | None = None       # populated for SQLQuery
    endpoint: str | None = None  # populated for EndpointQuery

    def __post_init__(self) -> None:
        """Auto-populate sql/endpoint from the request if not explicitly set."""
        if self.sql is None and isinstance(self.request.query, SQLQuery):
            object.__setattr__(self, "sql", self.request.query.sql)
        if self.endpoint is None and isinstance(self.request.query, EndpointQuery):
            object.__setattr__(self, "endpoint", self.request.query.endpoint)


@dataclass(frozen=True)
class DataResponse:
    """Normalised adapter output — the typed output side of the gateway contract.

    All three adapters (SQL, API, File) produce a DataResponse from their
    execute() method. Services and callers work with this type rather than
    raw dicts.
    """

    status: str                        # "success" | "error"
    data: list[dict[str, Any]]
    columns: list[ColumnMeta]
    rows_returned: int
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == "success"
