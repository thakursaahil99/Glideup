"""Vercel entrypoint: the Python runtime serves this module's ASGI `app`."""

from app.main import app

__all__ = ["app"]
