from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

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


class DetectionControlCommand(Base):
    __tablename__ = "detection_control_commands"

    device_id = Column(String(100), primary_key=True, nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    command_id = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    acknowledged_enabled = Column(Boolean, nullable=True)
    acknowledged_command_id = Column(String(64), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)


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
    scientific_name = Column(String(200), nullable=True)
    common_name = Column(String(150), nullable=True)

    confidence = Column(Float, nullable=True)
    top_predictions = Column(Text, nullable=True)
    insect_group = Column(String(100), nullable=True)
    group_score = Column(Float, nullable=True)

    risk = Column(String(50), nullable=True)
    risk_rationale = Column(Text, nullable=True)
    affected_crops = Column(Text, nullable=True)
    metadata_source_name = Column(String(200), nullable=True)
    metadata_source_url = Column(String(1000), nullable=True)

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


class Crop(Base):
    __tablename__ = "crops"

    crop_id = Column(String(100), primary_key=True)
    name = Column(String(150), nullable=False)
    category = Column(String(100), nullable=False)
    aliases = Column(JSON, nullable=False, default=list)


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


class PestCropSolution(Base):
    __tablename__ = "pest_crop_solutions"
    __table_args__ = (
        UniqueConstraint(
            "pest_id",
            "crop_id",
            "risk_level",
            name="uq_pest_crop_solution_identity",
        ),
    )

    solution_id = Column(String(300), primary_key=True)
    pest_id = Column(
        String(100),
        ForeignKey("pests.pest_id"),
        nullable=False,
        index=True,
    )
    crop_id = Column(
        String(100),
        ForeignKey("crops.crop_id"),
        nullable=False,
        index=True,
    )
    risk_level = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="NEEDS_REVIEW")
    region = Column(String(150), nullable=True)
    scientific_name = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    identification_signs = Column(Text, nullable=True)
    crop_damage = Column(Text, nullable=True)
    affected_plant_parts = Column(Text, nullable=True)
    recommended_treatment = Column(Text, nullable=True)
    immediate_control_measures = Column(Text, nullable=True)
    biological_control_options = Column(Text, nullable=True)
    cultural_control_methods = Column(Text, nullable=True)
    mechanical_control_methods = Column(Text, nullable=True)
    chemical_control_options = Column(Text, nullable=True)
    prevention = Column(Text, nullable=True)
    monitoring = Column(Text, nullable=True)
    safety_precautions = Column(Text, nullable=True)
    expert_advice = Column(Text, nullable=True)
    source_references = Column(JSON, nullable=False, default=list)
    reviewed_on = Column(String(10), nullable=True)


class PestSolutionCoverage(Base):
    __tablename__ = "pest_solution_coverage"

    pest_id = Column(
        String(100),
        ForeignKey("pests.pest_id"),
        primary_key=True,
    )
    review_status = Column(String(20), nullable=False, default="NEEDS_REVIEW")
    unresolved_fields = Column(JSON, nullable=False, default=list)
    reviewed_on = Column(String(10), nullable=True)
    research_data = Column(JSON, nullable=True)


class HighRiskSolutionHistory(Base):
    __tablename__ = "high_risk_solution_history"

    id = Column(Integer, primary_key=True, index=True)

    detection_id = Column(
        Integer,
        index=True,
        nullable=False,
    )

    device_id = Column(
        String(100),
        index=True,
        nullable=False,
    )

    pest_id = Column(
        String(100),
        index=True,
        nullable=True,
    )

    pest = Column(
        String(150),
        nullable=True,
    )

    common_name = Column(
        String(150),
        nullable=True,
    )

    image_url = Column(
        String(500),
        nullable=True,
    )

    risk = Column(
        String(50),
        nullable=False,
        default="HIGH",
    )

    confidence = Column(
        Float,
        nullable=True,
    )

    temperature = Column(
        Float,
        nullable=True,
    )

    humidity = Column(
        Float,
        nullable=True,
    )

    solution_title = Column(
        String(200),
        nullable=True,
    )

    solution_source = Column(
        String(20),
        nullable=True,
    )

    solution_description = Column(
        Text,
        nullable=True,
    )

    recommended_action = Column(
        Text,
        nullable=True,
    )

    prevention = Column(
        Text,
        nullable=True,
    )

    detected_at = Column(
        DateTime,
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )