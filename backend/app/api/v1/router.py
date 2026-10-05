from fastapi import APIRouter

from app.api.v1 import admin, admin_jobs, auth, jobs, matches, portfolio, resumes, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resumes.router)
api_router.include_router(portfolio.router)
api_router.include_router(jobs.router)
api_router.include_router(matches.router)
api_router.include_router(admin.router)
api_router.include_router(admin_jobs.router)
