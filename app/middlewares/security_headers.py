from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        allowed_frame_ancestors = [
            "'self'",
            "https://guiasrapidas1.salta.gob.ar",
            "https://salta.gob.ar",
            "https://www.salta.gob.ar",
            "https://*.salta.gob.ar",
            "http://localhost:8888",
            "http://127.0.0.1:8888",
            "https://localhost:8888",
            "https://127.0.0.1:8888",
        ]

        csp = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            f"frame-ancestors {' '.join(allowed_frame_ancestors)}; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp

        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response