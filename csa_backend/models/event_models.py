from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# Represents a speaker associated with an event
class Speaker(BaseModel):
    name: str  # Full name of the speaker
    role: str  # Role of the speaker (e.g., Panelist, Keynote)
    company: Optional[str]  # Company name (optional)
    image_url: Optional[str]  # Profile image URL (optional)
    about: Optional[str]  # Short bio or description (optional)

# Represents a single agenda item/session in the event schedule
class AgendaItem(BaseModel):
    duration: str  # Time duration in format like "5:30 PM - 6:00 PM"
    topic: str  # Topic title
    description: Optional[str]  # Description of the session (optional)

# Full event model used when creating or displaying an event
class Event(BaseModel):
    title: str  # Title of the event
    date_time: datetime  # Start date and time of the event
    slug: str  # URL-friendly unique identifier
    location: str  # Physical or virtual location
    checkins: str
    excerpt: str  # Short summary shown on previews or listings
    description: Optional[str]  # Full description (optional)
    
    # List of agenda items (each with topic, duration, description)
    agenda: List[AgendaItem] = Field(default_factory=list)
    
    # List of speakers (each with name, role, company, etc.)
    speakers: List[Speaker] = Field(default_factory=list)
    
    # List of tags or topics (e.g., ["AI", "Blockchain"])
    tags: List[str] = Field(default_factory=list)
    
    reg_url: Optional[str]  # Registration URL (optional)
    map_url: Optional[str]  # Map location URL (optional)
    capacity: int  # Total capacity for the event
    attendees: int = 0  # Current number of registered attendees