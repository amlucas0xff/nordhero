from typing import List, Optional
from pydantic import BaseModel, Field

class Technology(BaseModel):
    identifier: str
    metadata: List[dict]

class City(BaseModel):
    name: str

class Country(BaseModel):
    name: str
    city: City

class Location(BaseModel):
    country: Country

class WireGuardServer(BaseModel):
    hostname: str
    station: str  # IP address
    locations: List[Location]
    load: int
    technologies: List[Technology]

class WireGuardServerInfo(BaseModel):
    hostname: str
    ip: str
    country: str
    city: str
    load: int
    public_key: str = Field(alias="publicKey")
