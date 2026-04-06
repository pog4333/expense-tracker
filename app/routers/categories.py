from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db

router = APIRouter(prefix="/categories")
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def categories_page(request: Request):
    db  = get_db()
    hid = request.state.user["household_id"]
    all_cats = db.table("categories").select("id,name,parent_id,sort_order") \
        .eq("household_id", hid).order("sort_order").execute()
    if not all_cats.data:
        all_cats = db.table("categories").select("id,name,parent_id,sort_order") \
            .order("sort_order").execute()
    parents  = [c for c in all_cats.data if c["parent_id"] is None]
    children = [c for c in all_cats.data if c["parent_id"] is not None]
    for p in parents:
        p["subcategories"] = [c for c in children if c["parent_id"] == p["id"]]
    return templates.TemplateResponse("categories/index.html", {
        "request": request,
        "user": request.state.user,
        "categories": parents,
        "error":   request.query_params.get("error", ""),
        "success": request.query_params.get("success", ""),
    })


@router.post("/add")
@login_required
async def add_category(
    request: Request,
    name: str      = Form(...),
    parent_id: str = Form(""),
):
    db  = get_db()
    hid = request.state.user["household_id"]
    db.table("categories").insert({
        "name": name.strip(),
        "parent_id": parent_id or None,
        "household_id": hid,
    }).execute()
    return RedirectResponse(url="/categories/?success=Category+added", status_code=302)


@router.post("/add-inline")
@login_required
async def add_category_inline(
    request: Request,
    name: str      = Form(...),
    parent_id: str = Form(""),
):
    """Called from transaction add form via JS. Returns JSON."""
    db  = get_db()
    hid = request.state.user["household_id"]
    result = db.table("categories").insert({
        "name": name.strip(),
        "parent_id": parent_id or None,
        "household_id": hid,
    }).execute()
    if result.data:
        return JSONResponse({"id": result.data[0]["id"], "name": name.strip(), "parent_id": parent_id or None})
    return JSONResponse({"error": "Failed"}, status_code=500)


@router.post("/{cat_id}/edit")
@login_required
async def edit_category(
    request: Request, cat_id: str,
    name: str = Form(...),
):
    hid = request.state.user["household_id"]
    get_db().table("categories").update({"name": name.strip()}) \
        .eq("id", cat_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/categories/?success=Renamed", status_code=302)


@router.post("/{cat_id}/delete")
@login_required
async def delete_category(request: Request, cat_id: str):
    db  = get_db()
    hid = request.state.user["household_id"]
    tx  = db.table("transactions").select("id").eq("category_id", cat_id).limit(1).execute()
    if tx.data:
        return RedirectResponse(
            url="/categories/?error=Cannot+delete+a+category+that+has+transactions",
            status_code=302
        )
    db.table("categories").delete().eq("id", cat_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/categories/?success=Deleted", status_code=302)
