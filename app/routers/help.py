from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required

router = APIRouter(prefix="/help")
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def help_page(request: Request):
    return templates.TemplateResponse("help/index.html", {
        "request": request,
        "user": request.state.user,
    })
