"""SqlExpr — annotated string type marking fields that contain SQL expressions.

Fields typed as ``SqlExpr`` carry ``is_sql=True`` metadata so that vault
validation can parse them with sqlglot before persisting.

Usage::

    class Metric(BaseModel):
        sql: SqlExpr = ""
"""

from typing import Annotated

from pydantic import Field

SqlExpr = Annotated[str, Field(json_schema_extra={"is_sql": True})]
