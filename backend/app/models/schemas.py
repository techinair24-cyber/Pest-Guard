from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DetectionPayload(BaseModel):
    device_id: str = Field(min_length=1)
    pest: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    status: str
    risk: str = 'UNKNOWN'
    timestamp: Optional[datetime] = None


class AudioPrediction(BaseModel):
    pest: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    status: str
    risk: str = 'UNKNOWN'


class DeviceDetectionPayload(BaseModel):
    device_id: str = Field(min_length=1)
    audio_prediction: AudioPrediction
    vibration: bool
    timestamp: Optional[datetime] = None


class DeviceRegistration(BaseModel):
    device_id: str = Field(min_length=1)
    name: str = 'Field Unit'
    microphone_status: str = 'CONNECTED'
    vibration_status: str = 'CONNECTED'
    ai_status: str = 'READY'


class DetectionResponse(BaseModel):
    id: int
    device_id: str
    pest: Optional[str]
    confidence: float
    status: str
    risk: str
    timestamp: datetime
