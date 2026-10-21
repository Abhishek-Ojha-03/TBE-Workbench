"""
Pydantic Schemas for AI Responses.
Enforces strict JSON schema validation for all LLM calls.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ExtractedRequirement(BaseModel):
    """Schema for a single extracted technical or qualification requirement."""
    clause: Optional[str] = Field(default=None, description="Clause or section number, e.g. '5.2' or 'QR-1'")
    text: str = Field(description="Exact requirement text or description")
    is_qualification_requirement: bool = Field(
        default=False, 
        description="True ONLY if under explicit Qualification Requirements heading in the tender"
    )
    is_mandatory_document: bool = Field(
        default=False,
        description="True if this is a mandatory document requirement (e.g. Technical Offer, Deviation Sheet)"
    )
    standards: Optional[List[str]] = Field(default_factory=list, description="Applicable IS/IEC standards cited")
    page: int = Field(description="1-based page number where this requirement was found")


class SpecificationExtractionResult(BaseModel):
    """Schema for complete specification parsing result."""
    requirements: List[ExtractedRequirement] = Field(description="List of extracted requirements")


class VerificationFinding(BaseModel):
    """Schema for Step 7 Bidder verification finding per cell."""
    status: str = Field(description="Suggested status: 'complied', 'not_complied', or 'needs_human_review'")
    document: str = Field(description="Name of the document cited as evidence")
    page: int = Field(description="Page number where the evidence is found")
    quote: str = Field(description="Verbatim exact sentence cited as proof from that page")
    reason: str = Field(description="Technical rationale explaining why the evidence complies or fails")

