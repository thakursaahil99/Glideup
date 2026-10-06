from fastapi import APIRouter

from app.api.v1 import (
    admin,
    admin_interviews,
    admin_jobs,
    admin_prompts,
    admin_questions,
    auth,
    internal,
    interviews,
    jobs,
    matches,
    platform,
    portfolio,
    problems,
    resumes,
    skills,
    tracker,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resumes.router)
api_router.include_router(portfolio.router)
api_router.include_router(jobs.router)
api_router.include_router(matches.router)
api_router.include_router(interviews.router)
api_router.include_router(problems.router)
api_router.include_router(skills.router)
api_router.include_router(tracker.router)
api_router.include_router(platform.router)
api_router.include_router(admin.router)
api_router.include_router(admin_jobs.router)
api_router.include_router(admin_interviews.router)
api_router.include_router(admin_prompts.router)
api_router.include_router(admin_questions.router)
api_router.include_router(internal.router)
