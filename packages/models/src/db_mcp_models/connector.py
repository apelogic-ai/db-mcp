"""Versioned connector.yaml contract models and schema utilities."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from db_mcp_models.connector_capabilities import PROFILE_ALLOWED_TYPES, resolve_connector_profile

CONNECTOR_CONTRACT_SCHEMA_VERSION = "v1"
CONNECTOR_SPEC_VERSION = "1.0.0"
_SEMVER_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogMetadataContract(_StrictModel):
    """Optional metadata block for externally curated connector catalogs."""

    id: str
    version: str
    source: str | None = None
    url: str | None = None
    checksum: str | None = None


class FileSourceContract(_StrictModel):
    """File source definition for file connectors."""

    name: str
    path: str


class ConnectorContractV1(_StrictModel):
    """Versioned connector.yaml contract."""

    spec_version: str = Field(default=CONNECTOR_SPEC_VERSION)
    type: Literal["sql", "api", "file"] = "sql"
    profile: str = ""
    description: str = ""
    capabilities: dict[str, Any] = Field(default_factory=dict)

    # SQL connector fields
    database_url: str = ""

    # API connector fields
    base_url: str = ""
    spec_url: str = ""
    template_id: str = ""
    auth: dict[str, Any] = Field(default_factory=dict)
    endpoints: list[dict[str, Any]] = Field(default_factory=list)
    pagination: dict[str, Any] = Field(default_factory=dict)
    rate_limit: dict[str, Any] = Field(default_factory=dict)
    rate_limit_rps: float | None = None
    api_title: str = ""
    api_description: str = ""

    # File connector fields
    directory: str = ""
    sources: list[FileSourceContract] = Field(default_factory=list)

    # Optional external catalog metadata
    catalog: CatalogMetadataContract | None = None

    @field_validator("spec_version")
    @classmethod
    def _validate_spec_version(cls, value: str) -> str:
        match = _SEMVER_RE.match(value)
        if not match:
            raise ValueError(
                "spec_version must be semver (MAJOR.MINOR.PATCH), for example '1.0.0'."
            )
        major = int(match.group("major"))
        if major != 1:
            raise ValueError(
                f"Unsupported connector spec major version '{major}'. "
                "This db-mcp build supports major version 1."
            )
        return value

    @model_validator(mode="after")
    def _validate_type_and_profile(self) -> "ConnectorContractV1":
        if self.profile:
            allowed_types = PROFILE_ALLOWED_TYPES.get(self.profile)
            if allowed_types is None:
                if not self.profile.startswith("x-"):
                    known = ", ".join(sorted(PROFILE_ALLOWED_TYPES.keys()))
                    raise ValueError(
                        f"Unknown profile '{self.profile}'. Use one of [{known}] or "
                        "an extension profile prefixed with 'x-'."
                    )
            elif self.type not in allowed_types:
                supported = ", ".join(sorted(allowed_types))
                raise ValueError(
                    f"Profile '{self.profile}' is not compatible with connector type "
                    f"'{self.type}'. Supported type(s): {supported}."
                )

        if self.type == "api" and not self.base_url:
            raise ValueError("API connectors require 'base_url'.")
        if self.type == "file" and not self.directory and not self.sources:
            raise ValueError("File connectors require either 'directory' or non-empty 'sources'.")

        return self

    @property
    def effective_profile(self) -> str:
        """Return effective profile after default resolution."""
        return resolve_connector_profile(self.type, self.profile)


def validate_connector_contract(data: dict[str, Any]) -> ConnectorContractV1:
    """Validate and parse a connector.yaml document for v1 contract."""
    return ConnectorContractV1.model_validate(data)


def get_connector_contract_models() -> dict[str, type[BaseModel]]:
    """Return named connector contract models for schema export."""
    return {"connector": ConnectorContractV1}


def build_connector_contract_schemas() -> dict[str, dict[str, Any]]:
    """Build JSON schemas for connector contract models."""
    return {
        name: model.model_json_schema()
        for name, model in get_connector_contract_models().items()
    }


def format_validation_error(exc: ValidationError) -> list[str]:
    """Format pydantic validation errors for human-readable CLI output."""
    errors: list[str] = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err.get("loc", [])) or "<root>"
        message = err.get("msg", "validation error")
        errors.append(f"{location}: {message}")
    return errors
