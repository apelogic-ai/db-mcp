"""Generic executable semantic policy models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BoundaryMode(str, Enum):
    """How the runtime should render the end boundary for a time window."""

    INCLUSIVE = "inclusive"
    EXCLUSIVE_UPPER_BOUND = "exclusive_upper_bound"


class TimeWindowPolicy(BaseModel):
    """Executable time-window semantics for a family of tables or metrics."""

    applies_to: list[str] = Field(
        default_factory=list,
        description="Table family hints that this time-window policy applies to.",
    )
    end_inclusive: bool = Field(
        default=False,
        description="Whether natural-language 'ending on X' includes day X.",
    )
    end_parameter_mode: BoundaryMode = Field(
        default=BoundaryMode.INCLUSIVE,
        description="How the runtime should materialize the end boundary parameter.",
    )


class UnitConversionPolicy(BaseModel):
    """Executable unit conversion policy for data-volume metrics."""

    gb_divisor: int | None = Field(default=None, description="Bytes per GiB-like unit.")
    tb_divisor: int | None = Field(default=None, description="Bytes per TiB-like unit.")


class SemanticPolicy(BaseModel):
    """Connection-local executable semantic policy derived from knowledge artifacts."""

    provider_id: str = Field(..., description="Connection/provider identifier")
    time_windows: list[TimeWindowPolicy] = Field(
        default_factory=list,
        description="Available executable time-window policies.",
    )
    unit_conversion: UnitConversionPolicy | None = Field(
        default=None,
        description="Available executable data-volume conversion policy.",
    )

