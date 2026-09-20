from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False, default="Pest Guard Field Unit")
    status = Column(String(50), nullable=False, default="OFFLINE")
    connection = Column(String(50), nullable=False, default="DISCONNECTED")

    last_seen = Column(DateTime, nullable=True)

    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)

    device_id = Column(String(100), index=True, nullable=False)

    status = Column(
        String(50),
        nullable=False,
        default="UNKNOWN",
    )

    pest = Column(String(150), nullable=True)

    confidence = Column(Float, nullable=True)

    risk = Column(String(50), nullable=True)

    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)

    audio_file = Column(String(500), nullable=True)

    message = Column(Text, nullable=True)

    detected_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )


class Pest(Base):
    __tablename__ = "pests"

    id = Column(Integer, primary_key=True, index=True)

    pest_id = Column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    name = Column(String(150), nullable=False)

    scientific_name = Column(String(200), nullable=True)

    description = Column(Text, nullable=True)

    risk = Column(String(50), nullable=True)

    symptoms = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class Solution(Base):
    __tablename__ = "solutions"

    id = Column(Integer, primary_key=True, index=True)

    pest_id = Column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    title = Column(String(200), nullable=False)

    description = Column(Text, nullable=True)

    recommended_action = Column(Text, nullable=True)

    prevention = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )