from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DeviceBase(BaseModel):
    device_id: str
    name: str = "Pest Guard Field Unit"


class DeviceHeartbeat(BaseModel):
    status: str = "ONLINE"
    connection: str = "CONNECTED"
    temperature: Optional[float] = None
    humidity: Optional[float] = None


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
    pest: Optional[str] = None
    confidence: Optional[float] = None
    risk: Optional[str] = None
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


class HealthResponse(BaseModel):
    status: str
    service: str