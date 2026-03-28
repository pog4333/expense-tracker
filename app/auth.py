from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import SECRET_KEY
from app.database import anon_client, service_client
import functools

_signer = URLSafeTimedSerializer(SECRET_KEY)
COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def create_session_cookie(user_id: str, access_token: str, household_id: str = "") -> str:
    return _signer.dumps({"user_id": user_id, "access_token": access_token, "household_id": household_id})


def decode_session_cookie(cookie_value: str) -> dict | None:
    try:
        return _signer.loads(cookie_value, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def login_user(email: str, password: str) -> dict:
    try:
        response = anon_client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        user    = response.user
        session = response.session
        if not user or not session:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        profile = (
            service_client.table("profiles")
            .select("display_name, household_id")
            .eq("id", user.id)
            .single()
            .execute()
        )

        if not profile.data:
            raise HTTPException(status_code=401, detail="Profile not found — contact your admin")

        if not profile.data.get("household_id"):
            raise HTTPException(status_code=401, detail="No household assigned — contact your admin")

        return {
            "user_id":      user.id,
            "email":        user.email,
            "display_name": profile.data.get("display_name", email),
            "household_id": profile.data["household_id"],
            "access_token": session.access_token,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")


def get_current_user(request: Request) -> dict | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    return decode_session_cookie(cookie)


def login_required(func):
    @functools.wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return RedirectResponse(url="/login", status_code=302)
        if not user.get("household_id"):
            return RedirectResponse(url="/login", status_code=302)
        request.state.user = user
        return await func(request, *args, **kwargs)
    return wrapper
