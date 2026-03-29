from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_user, create_session_cookie, decode_session_cookie, COOKIE_NAME, COOKIE_MAX_AGE
from app.database import anon_client

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        session = decode_session_cookie(cookie)
        if session and session.get("household_id"):
            return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request, "error": error
    })


@router.post("/login")
async def login_submit(
    request: Request,
    email: str    = Form(...),
    password: str = Form(...),
):
    try:
        user = login_user(email, password)
    except Exception:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password"
        }, status_code=401)

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session_cookie(user["user_id"], user["access_token"], user["household_id"]),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {
        "request": request, "sent": False, "error": ""
    })


@router.post("/forgot-password")
async def forgot_password_submit(request: Request, email: str = Form(...)):
    try:
        host   = request.headers.get("host", "")
        scheme = "https" if "onrender.com" in host else "http"
        app_url = f"{scheme}://{host}"
        anon_client.auth.reset_password_email(
            email,
            options={"redirect_to": f"{app_url}/reset-password"}
        )
    except Exception:
        pass  # always show success — don't reveal if email exists
    return templates.TemplateResponse("forgot_password.html", {
        "request": request, "sent": True, "error": ""
    })


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    return templates.TemplateResponse("reset_password.html", {
        "request": request, "error": "", "success": False
    })


@router.post("/reset-password")
async def reset_password_submit(
    request: Request,
    access_token: str = Form(...),
    new_password: str = Form(...),
):
    try:
        anon_client.auth.set_session(access_token, access_token)
        anon_client.auth.update_user({"password": new_password})
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "error": "", "success": True
        })
    except Exception:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "error": "Link expired or invalid. Request a new one.",
            "success": False
        })
