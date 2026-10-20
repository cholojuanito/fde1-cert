
from enum import StrEnum

from pydantic import BaseModel, Field


class FindingType(StrEnum):
    MISSING_FIELD = "missing_field"
    INVALID_VALUE = "invalid_value"
    UNKNOWN_FIELD = "unknown_field"
    CONFLICTING_VALUES = "conflicting_values"
    MISSING_EVIDENCE = "missing_evidence"
    MISSING_STATEMENT = "missing_statement"
    INVALID_CODE = "invalid_code"
    OTHER = "other"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AuditFinding(BaseModel):
    form_id: str
    field_id: str | None = None
    finding_type: FindingType
    severity: FindingSeverity
    message: str

    resolved: bool = False
    resolution: str | None = None


class AuditResult(BaseModel):
    form_id: str
    findings: list[AuditFinding] = Field(
        default_factory=list
    )
    export_ready: bool = False
