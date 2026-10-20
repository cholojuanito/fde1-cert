from enum import StrEnum

class Parser(StrEnum):
    DOCLING = "docling"
    LITEPARSE = "liteparse"
    VLM = "vlm"

class ExtractionArtifactFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "md"

class ExtractionArtifactStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"

class DocumentElementType(StrEnum):
    TEXT = "text"
    HEADING = "heading"
    TABLE = "table"
    IMAGE = "image"
    KEY_VALUE = "key_value"
    FORM_FIELD = "form_field"
    OTHER = "other"

class ExtractionMethod(StrEnum):
    NATIVE_TEXT = "native_text"
    OCR = "ocr"
    VLM = "vlm"
    UNKNOWN = "unknown"

class TaxDocumentType(StrEnum):
    FEDERAL_1065_K1 = "1065_k1"
    FEDERAL_1065_K2 = "1065_k2"
    FEDERAL_1065_K3 = "1065_k3"
    FEDERAL_1120S_K1 = "1120s_k1"
    FEDERAL_1041_K1 = "1041_k1"
    STATE_K1 = "state_k1"
    SUPPLEMENTAL_STATEMENT = "supplemental_statement"
    OTHER = "other"
    UNKNOWN = "unknown"

class ReviewStatus(StrEnum):
    EXTRACTED = "extracted"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"

class State(StrEnum):
    UTAH = 'UT'
    DELAWARE = 'DE'

class PartnershipType(StrEnum):
    INDIVIDUAL = "I"
    CORPORATION = "C"
    S_CORP = "S"
    NONPROFIT = "N"
    GENERAL = "P"
    LIMITED = "L"
    LLC = "B"
    TRUST = "T"
    LLP = "R"
    OTHER = "O"
