from pydantic import BaseModel, HttpUrl, EmailStr
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class VolunteerApplication(BaseModel):
    # Basic personal details
    first_name: str  # First name of the volunteer
    last_name: str   # Last name of the volunteer
    email: EmailStr  # Validated email address

    # Professional background (optional)
    company: Optional[str] = None         # Current company or organization
    job_title: Optional[str] = None       # Current job title
    experience_level: Optional[str] = None  # e.g., Entry-level, Mid-level, Senior

    # Skills and interests
    skills: Optional[str] = None              # Relevant skills (e.g., "Python, Event Planning")
    volunteer_roles: List[str]                # Roles the volunteer is interested in (e.g., ["Speaker", "Organizer"])
    availability: Optional[str] = None        # Availability description (e.g., "Weekends only")
    motivation: Optional[str] = None          # Why the person wants to volunteer

    # Optional image (e.g., LinkedIn profile picture)
    img_url: Optional[str] = None             # URL to the volunteer’s image or avatar