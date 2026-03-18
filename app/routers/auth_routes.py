from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_user, create_session_cookie, COOKIE_NAME, COOKIE_MAX_AGE

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    # Already logged in? Go to dashboard
    if request.cookies.get(COOKIE_NAME):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error
    })


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
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
        value=create_session_cookie(user["user_id"], user["access_token"]),
        max_age=COOKIE_MAX_AGE,
        httponly=True,   # JS cannot read this cookie
        samesite="lax",
        secure=False     # set to True in production (HTTPS)
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
