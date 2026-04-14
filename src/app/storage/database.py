from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import Optional
import logging

from ..config.settings import settings

logger = logging.getLogger(__name__)

# SQLAlchemy setup
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AuditRecord(Base):
    """Audit record model for storing audit results"""
    __tablename__ = "audit_records"

    id = Column(Integer, primary_key=True, index=True)
    content_hash = Column(String(64), index=True)  # SHA-256 hash of content
    content_preview = Column(Text)  # First 500 chars of content
    result = Column(String(20))  # "approved", "rejected", "uncertain"
    confidence = Column(Float)
    reason = Column(Text)
    violated_rules = Column(JSON)  # List of violated rule IDs
    processing_path = Column(JSON)  # List of agents that processed this
    content_metadata = Column(JSON)  # Additional metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RuleVersion(Base):
    """Rule version model for tracking rule changes"""
    __tablename__ = "rule_versions"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(50), unique=True, index=True)
    rules_content = Column(JSON)  # Complete rule set
    source_document = Column(String(255))  # Original document filename
    extracted_by = Column(String(100))  # Agent or user who extracted
    validated_by = Column(String(100))  # Agent or user who validated
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    activated_at = Column(DateTime)


class AuditCase(Base):
    """Audit case model for storing training examples"""
    __tablename__ = "audit_cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(36), unique=True, index=True)  # UUID
    content = Column(Text)
    result = Column(String(20))  # "approved", "rejected"
    reason = Column(Text)
    source = Column(String(50))  # "manual", "ai_generated", "historical"
    rule_version_id = Column(Integer, index=True)
    vector_store_synced = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemLog(Base):
    """System log model for tracking system events"""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20))  # "INFO", "WARNING", "ERROR"
    component = Column(String(100))  # System component that generated the log
    event = Column(String(200))  # Event description
    details = Column(JSON)  # Additional event details
    created_at = Column(DateTime, default=datetime.utcnow)


def create_tables():
    """Create all database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatabaseService:
    """Database service for common operations"""

    def __init__(self):
        self.session_factory = SessionLocal

    def create_audit_record(
        self,
        content_hash: str,
        content_preview: str,
        result: str,
        confidence: float,
        reason: str,
        violated_rules: list,
        processing_path: list,
        metadata: Optional[dict] = None
    ) -> AuditRecord:
        """Create new audit record"""
        with self.session_factory() as db:
            record = AuditRecord(
                content_hash=content_hash,
                content_preview=content_preview,
                result=result,
                confidence=confidence,
                reason=reason,
                violated_rules=violated_rules,
                processing_path=processing_path,
                content_metadata=metadata or {}
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record

    def get_active_rule_version(self) -> Optional[RuleVersion]:
        """Get currently active rule version"""
        with self.session_factory() as db:
            return db.query(RuleVersion).filter(RuleVersion.is_active == True).first()

    def create_rule_version(
        self,
        version: str,
        rules_content: dict,
        source_document: str,
        extracted_by: str,
        validated_by: Optional[str] = None
    ) -> RuleVersion:
        """Create new rule version"""
        with self.session_factory() as db:
            # Deactivate current active version
            active_version = db.query(RuleVersion).filter(RuleVersion.is_active == True).first()
            if active_version:
                active_version.is_active = False

            # Create new version
            rule_version = RuleVersion(
                version=version,
                rules_content=rules_content,
                source_document=source_document,
                extracted_by=extracted_by,
                validated_by=validated_by,
                is_active=True,
                activated_at=datetime.utcnow()
            )
            db.add(rule_version)
            db.commit()
            db.refresh(rule_version)
            return rule_version

    def log_system_event(
        self,
        level: str,
        component: str,
        event: str,
        details: Optional[dict] = None
    ):
        """Log system event"""
        with self.session_factory() as db:
            log_entry = SystemLog(
                level=level,
                component=component,
                event=event,
                details=details or {}
            )
            db.add(log_entry)
            db.commit()

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.session_factory() as db:
                db.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False


# Global database service instance
db_service = DatabaseService()