from fastapi import Request, HTTPException


def require_admin_session(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=401, detail="No autenticado")
    return True