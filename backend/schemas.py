from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DeviceBase(BaseModel):
    device_id: str
    name: str = "Pest Guard Field Unit"


class DeviceHeartbeat(BaseModel):
    status: str = "ONLINE"
    connection: str = "CONNECTED"
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    detection_enabled: Optional[bool] = None
    control_command_id: Optional[str] = Field(default=None, max_length=64)


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    name: str
    status: str
    connection: str
    last_seen: Optional[datetime] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None


class DetectionCreate(BaseModel):
    device_id: str

    status: str
    pest: Optional[str] = None
    confidence: Optional[float] = None
    risk: Optional[str] = None

    temperature: Optional[float] = None
    humidity: Optional[float] = None

    audio_file: Optional[str] = None
    message: Optional[str] = None

    detected_at: Optional[datetime] = None


class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    status: str
    identification_status: Optional[str] = None
    identification_label: Optional[str] = None
    source: Optional[str] = None
    pest: Optional[str] = None
    pest_id: Optional[str] = None
    pest_verified: bool = False
    scientific_name: Optional[str] = None
    common_name: Optional[str] = None
    confidence: Optional[float] = None
    insect_group: Optional[str] = None
    group_score: Optional[float] = None
    risk: Optional[str] = None
    risk_rationale: Optional[str] = None
    affected_crops: list[str] = Field(default_factory=list)
    metadata_source_name: Optional[str] = None
    metadata_source_url: Optional[str] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    audio_file: Optional[str] = None
    message: Optional[str] = None
    detected_at: datetime


class PestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pest_id: str
    name: str
    scientific_name: Optional[str] = None
    description: Optional[str] = None
    risk: Optional[str] = None
    symptoms: Optional[str] = None


class SolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pest_id: str
    title: str
    description: Optional[str] = None
    recommended_action: Optional[str] = None
    prevention: Optional[str] = None


class CropResponse(BaseModel):
    crop_id: str
    name: str
    category: str
    aliases: list[str] = Field(default_factory=list)


class SolutionSourceResponse(BaseModel):
    title: str
    organization: str
    url: str
    reviewed_on: Optional[str] = None
    supports: list[str] = Field(default_factory=list)


class PestCropSolutionResponse(BaseModel):
    solution_id: str
    pest_id: str
    pest_name: str
    insect_group: str
    risk: Literal["HIGH", "MEDIUM", "LOW"]
    crop_id: str
    crop_name: str
    region: Optional[str] = None
    description: Optional[str] = None
    identification_signs: Optional[str] = None
    crop_damage: Optional[str] = None
    affected_plant_parts: Optional[str] = None
    recommended_treatment: Optional[str] = None
    immediate_control_measures: Optional[str] = None
    biological_control_options: Optional[str] = None
    cultural_control_methods: Optional[str] = None
    mechanical_control_methods: Optional[str] = None
    chemical_control_options: Optional[str] = None
    prevention: Optional[str] = None
    monitoring: Optional[str] = None
    safety_precautions: Optional[str] = None
    expert_advice: Optional[str] = None
    source_references: list[SolutionSourceResponse]
    reviewed_on: Optional[str] = None


class PestCropSolutionListResponse(BaseModel):
    crop: CropResponse
    total: int
    solutions: list[PestCropSolutionResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str