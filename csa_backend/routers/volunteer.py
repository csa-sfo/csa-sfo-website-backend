from fastapi import APIRouter, HTTPException
from datetime import datetime
from supabase import create_client, Client
import os
from models.volunteers_models import VolunteerApplication
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize the router
volunteer_router = APIRouter()

# Load Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # Use service role key for secure inserts
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@volunteer_router.post("/volunteers")
async def submit_volunteer_application(application: VolunteerApplication):
    """
    Submit a new volunteer application to the Supabase 'volunteers' table.

    Args:
        application (VolunteerApplication): Parsed request body containing volunteer info.

    Returns:
        JSON response with status and submitted data or error message.
    """
    try:
        # Prepare data for insertion
        volunteer_data = {
            "first_name": application.first_name,
            "last_name": application.last_name,
            "email": application.email,
            "company": application.company,
            "job_title": application.job_title,
            "experience_level": application.experience_level,
            "skills": application.skills,
            "volunteer_roles": application.volunteer_roles,  # Should be stored as text[]
            "availability": application.availability,
            "motivation": application.motivation,
            "img_url": application.img_url,
            "submitted_at": datetime.utcnow().isoformat()  # Store UTC timestamp
        }

        # Insert into Supabase
        response = supabase.table("volunteers").insert(volunteer_data).execute()

        # Handle insert result
        if not response.data:
            logging.error(f"Failed to insert volunteer application: {response}")
            raise HTTPException(status_code=500, detail="Failed to submit application")

        logging.info(f"Volunteer application submitted successfully: ID {response.data[0]['id']}")
        return {
            "message": "Application submitted successfully",
            "data": response.data
        }

    except Exception as e:
        logging.exception("Exception occurred while submitting volunteer application")
        raise HTTPException(status_code=500, detail=str(e))