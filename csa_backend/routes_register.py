from fastapi import APIRouter



from routers.test import router as  test_router
from routers.router import message_router
from routers.contact import contact_router
# from routers.mcp_router import router as mcp_router
from routers.search import search_router
from routers.auth import auth_router
from routers.auth_linkedin import linkedin_router
from routers.linkedin_mcp_router import linkedin_mcp_router
from routers.social_agent_router import social_agent_router
from routers.event import event_router
from routers.event_registration import event_registration_router
from routers.volunteer import volunteer_router
from routers.upload import upload_router
from routers.event_images import event_images_router
# Register all routers here


router = APIRouter()

router.include_router(message_router, tags=["message"])
router.include_router(test_router, tags=["test"])
router.include_router(contact_router, tags=["contact"])
# router.include_router(mcp_router, tags=["mcp"])
router.include_router(search_router, tags=["search"])
router.include_router(auth_router, tags=["basiclogin"])
router.include_router(auth_router,tags=["googlelogin"])
router.include_router(linkedin_router, tags=["linkedinlogin"])
router.include_router(linkedin_mcp_router, tags=["linkedin"])
router.include_router(social_agent_router, tags=["social-agent"])
router.include_router(event_router,tags=["events"])
router.include_router(event_registration_router, tags=["event-registrations"])
router.include_router(volunteer_router,tags=["volunteers"])
router.include_router(upload_router, tags=["upload"])
router.include_router(event_images_router, prefix="/event-images", tags=["event-images"])
