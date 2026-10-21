"""
SQLAlchemy models matching the Developer Guide specification.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Text, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from db.connection import Base


class Tender(Base):
    """
    Tender: One purchase process with a description and a NIT number.
    Status: 'open' or 'completed'
    """
    __tablename__ = "tenders"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String(500), nullable=False)
    nit_no = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(50), default="open", nullable=False)  # 'open' | 'completed'
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    baseline_versions = relationship("BaselineVersion", back_populates="tender", cascade="all, delete-orphan")
    bidders = relationship("Bidder", back_populates="tender", cascade="all, delete-orphan")


class BaselineVersion(Base):
    """
    BaselineVersion: Version history of approved requirements.
    Version 1 is approved initial baseline. Edits create Version 2, etc.
    """
    __tablename__ = "baseline_versions"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id"), nullable=False)
    version_number = Column(Integer, default=1, nullable=False)
    approved_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tender = relationship("Tender", back_populates="baseline_versions")
    requirements = relationship("Requirement", back_populates="baseline_version", cascade="all, delete-orphan")


class Requirement(Base):
    """
    Requirement: One technical/qualification item to satisfy.
    is_QR: True if it belongs under Qualification Requirements heading.
    """
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, index=True)
    baseline_version_id = Column(Integer, ForeignKey("baseline_versions.id"), nullable=False)
    clause = Column(String(50), nullable=True)
    text = Column(Text, nullable=False)
    is_QR = Column(Boolean, default=False, nullable=False)
    not_applicable = Column(Boolean, default=False, nullable=False)

    # Relationships
    baseline_version = relationship("BaselineVersion", back_populates="requirements")
    findings = relationship("Finding", back_populates="requirement", cascade="all, delete-orphan")


class Bidder(Base):
    """
    Bidder: A vendor participating in the tender.
    final_status: 'Pending', 'Qualified', 'Not Qualified'
    """
    __tablename__ = "bidders"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id"), nullable=False)
    name = Column(String(200), nullable=False)
    final_status = Column(String(50), default="Pending", nullable=False)  # 'Pending' | 'Qualified' | 'Not Qualified'

    # Relationships
    tender = relationship("Tender", back_populates="bidders")
    documents = relationship("Document", back_populates="bidder", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="bidder", cascade="all, delete-orphan")


class Document(Base):
    """
    Document: An uploaded file belonging to a bidder or tender specification.
    document_type: 'Technical Offer', 'Deviation Sheet', 'Type Test Report', 'Specification', etc.
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    bidder_id = Column(Integer, ForeignKey("bidders.id"), nullable=True)  # Null if it's the Tender Specification
    file_name = Column(String(300), nullable=False)
    file_path = Column(String(500), nullable=True)
    document_type = Column(String(100), nullable=True)

    # Relationships
    bidder = relationship("Bidder", back_populates="documents")
    pages = relationship("Page", back_populates="document", cascade="all, delete-orphan")


class Page(Base):
    """
    Page: Single page of a document.
    read_by: 'PyMuPDF' or 'LLM' (Vision)
    """
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)  # 1-indexed
    text = Column(Text, nullable=False)
    read_by = Column(String(50), default="PyMuPDF", nullable=False)  # 'PyMuPDF' | 'LLM'
    image_path = Column(String(500), nullable=True)

    # Relationships
    document = relationship("Document", back_populates="pages")
    evidences = relationship("Evidence", back_populates="page", cascade="all, delete-orphan")


class Finding(Base):
    """
    Finding: Represents ONE CELL in the TBE matrix (One Requirement x One Bidder).
    ai_status: suggested by AI ('Complied', 'Not Complied', 'Needs Human Review')
    engineer_status: confirmed by human engineer ('Complied', 'Not Complied', 'Needs Human Review', 'N/A')
    needs_recheck: flagged when new documents, baseline changes, or clarifications arrive.
    """
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    bidder_id = Column(Integer, ForeignKey("bidders.id"), nullable=False)
    ai_status = Column(String(50), default="Needs Human Review", nullable=False)
    engineer_status = Column(String(50), nullable=True)
    remark = Column(Text, nullable=True)
    needs_recheck = Column(Boolean, default=False, nullable=False)

    # Relationships
    requirement = relationship("Requirement", back_populates="findings")
    bidder = relationship("Bidder", back_populates="findings")
    evidences = relationship("Evidence", back_populates="finding", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="finding", cascade="all, delete-orphan")


class Evidence(Base):
    """
    Evidence: Verifiable quote and page reference linked to a finding.
    """
    __tablename__ = "evidences"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(Integer, ForeignKey("findings.id"), nullable=False)
    page_id = Column(Integer, ForeignKey("pages.id"), nullable=False)
    quoted_text = Column(Text, nullable=False)

    # Relationships
    finding = relationship("Finding", back_populates="evidences")
    page = relationship("Page", back_populates="evidences")


class AuditLog(Base):
    """
    AuditLog: Immutable change log for compliance and traceability.
    Tracks every human confirmation, override, and comment.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(Integer, ForeignKey("findings.id"), nullable=False)
    who = Column(String(100), default="Engineer", nullable=False)
    what_changed = Column(String(100), nullable=False)  # e.g., 'engineer_status', 'remark'
    old_value = Column(String(200), nullable=True)
    new_value = Column(String(200), nullable=True)
    reason = Column(Text, nullable=True)  # Mandatory for overrides
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    finding = relationship("Finding", back_populates="audit_logs")

