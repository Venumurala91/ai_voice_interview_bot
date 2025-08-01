from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from database import Base # Direct import
import uuid
from datetime import datetime

class Interview(Base):
    __tablename__ = "interviews"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_name = Column(String, nullable=False)
    candidate_phone = Column(String, nullable=False)
    job_position = Column(String, nullable=False)
    status = Column(String, default="created")
    questions = Column(JSON, nullable=True)
    responses = Column(JSON, nullable=True, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)