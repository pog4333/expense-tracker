from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db
from decimal import Decimal

router = APIRouter(prefix="/transactions")
templates = Jinja2Templates(directory="app/templates")


def _get_form_data(db):
    accounts = db.table("accounts").select("id,name,type").eq("is_active", True).order("name").execute()
    buckets  = db.table("buckets").select("id,name").eq("is_active", True).order("sort_order").execute()
    all_cats = db.table("categories").select("id,name,parent_id").order("sort_order").execute()
    parents  = [c for c in all_cats.data if c["parent_id"] is None]
    children = [c for c in all_cats.data if c["parent_id"] is not None]
    for p in parents:
        p["subcategories"] = [c for c in children if c["parent_id"] == p["id"]]
    return accounts.data, buckets.data, parents


@router.get("/", response_class=HTMLResponse)
@login_required
async def transaction_list(request: Request):
    db = get_db()
    result = (
        db.table("v_transactions")
        .select("*")
        .is_("split_parent_id", None)
        .order("date", desc=True)
        .limit(100)
        .execute()
    )
    return templates.TemplateResponse("transactions/list.html", {
        "request": request, "user": request.state.user,
        "transactions": result.data,
    })


@router.get("/add", response_class=HTMLResponse)
@login_required
async def add_transaction_page(request: Request, merchant: str = ""):
    db = get_db()
    accounts, buckets, categories = _get_form_data(db)
    autofill = None
    if merchant:
        m = db.table("v_merchant_suggestions").select("*").ilike("name", merchant).limit(1).execute()
        autofill = m.data[0] if m.data else None
    return templates.TemplateResponse("transactions/add.html", {
        "request": request, "user": request.state.user,
        "accounts": accounts, "buckets": buckets,
        "categories": categories, "autofill": autofill,
        "merchant_query": merchant,
    })


@router.post("/add")
@login_required
async def add_transaction(
    request: Request,
    date: str          = Form(...),
    merchant_name: str = Form(...),
    amount: str        = Form(...),
    account_id: str    = Form(...),
    bucket_id: str     = Form(...),
    category_id: str   = Form(...),
    note: str          = Form(""),
    is_salary: bool    = Form(False),
):
    db   = get_db()
    user = request.state.user
    tx_data = {
        "type": "income" if is_salary else "expense",
        "date": date, "merchant_name": merchant_name.strip(),
        "amount": str(Decimal(amount)),
        "account_id": account_id, "bucket_id": bucket_id,
        "category_id": category_id, "note": note.strip() or None,
        "is_salary": is_salary, "entered_by": user["user_id"],
    }
    result = db.table("transactions").insert(tx_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save transaction")
    if is_salary:
        db.rpc("process_salary_deposit", {
            "p_transaction_id": result.data[0]["id"],
            "p_amount": str(Decimal(amount))
        }).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


@router.get("/{tx_id}/edit", response_class=HTMLResponse)
@login_required
async def edit_transaction_page(request: Request, tx_id: str):
    db = get_db()
    result = db.table("v_transactions").select("*").eq("id", tx_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Not found")
    accounts, buckets, categories = _get_form_data(db)
    return templates.TemplateResponse("transactions/edit.html", {
        "request": request, "user": request.state.user,
        "tx": result.data, "accounts": accounts,
        "buckets": buckets, "categories": categories,
    })


@router.post("/{tx_id}/edit")
@login_required
async def edit_transaction(
    request: Request, tx_id: str,
    date: str          = Form(...),
    merchant_name: str = Form(...),
    amount: str        = Form(...),
    account_id: str    = Form(...),
    bucket_id: str     = Form(...),
    category_id: str   = Form(...),
    note: str          = Form(""),
):
    db = get_db()
    db.table("transactions").update({
        "date": date, "merchant_name": merchant_name.strip(),
        "amount": str(Decimal(amount)), "account_id": account_id,
        "bucket_id": bucket_id, "category_id": category_id,
        "note": note.strip() or None,
    }).eq("id", tx_id).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


@router.post("/{tx_id}/delete")
@login_required
async def delete_transaction(request: Request, tx_id: str):
    get_db().table("transactions").delete().eq("id", tx_id).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


@router.post("/{tx_id}/refund/request")
@login_required
async def request_refund(request: Request, tx_id: str):
    get_db().table("transactions").update({"refund_status": "pending"}).eq("id", tx_id).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


@router.post("/{tx_id}/refund/confirm")
@login_required
async def confirm_refund(request: Request, tx_id: str, date: str = Form(...), amount: str = Form(...)):
    db   = get_db()
    orig = db.table("transactions").select("*").eq("id", tx_id).single().execute().data
    if not orig:
        raise HTTPException(status_code=404, detail="Not found")
    db.table("transactions").insert({
        "type": "income", "date": date,
        "merchant_name": f"Refund – {orig['merchant_name']}",
        "amount": str(Decimal(amount)),
        "account_id": orig["account_id"], "bucket_id": orig["bucket_id"],
        "category_id": orig["category_id"], "refund_of_id": tx_id,
        "note": "Refund confirmed", "entered_by": request.state.user["user_id"],
    }).execute()
    db.table("transactions").update({"refund_status": "confirmed"}).eq("id", tx_id).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


@router.get("/transfer", response_class=HTMLResponse)
@login_required
async def transfer_page(request: Request):
    db = get_db()
    accounts = db.table("accounts").select("id,name,type").eq("is_active", True).order("name").execute()
    buckets  = db.table("buckets").select("id,name").eq("is_active", True).order("sort_order").execute()
    return templates.TemplateResponse("transactions/transfer.html", {
        "request": request, "user": request.state.user,
        "accounts": accounts.data, "buckets": buckets.data,
    })


@router.post("/transfer")
@login_required
async def create_transfer(
    request: Request,
    transfer_type: str = Form(...),
    date: str          = Form(...),
    amount: str        = Form(...),
    from_id: str       = Form(...),
    to_id: str         = Form(...),
    note: str          = Form(""),
):
    db      = get_db()
    tx_data = {
        "type": "transfer", "transfer_type": transfer_type,
        "date": date, "merchant_name": "Transfer",
        "amount": str(Decimal(amount)),
        "note": note.strip() or None,
        "entered_by": request.state.user["user_id"],
    }
    if transfer_type in ("account", "cc_payment"):
        tx_data["from_account_id"] = from_id
        tx_data["to_account_id"]   = to_id
    else:
        tx_data["from_bucket_id"] = from_id
        tx_data["to_bucket_id"]   = to_id
    db.table("transactions").insert(tx_data).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


@router.get("/merchant-suggest")
@login_required
async def merchant_suggest(request: Request, q: str = ""):
    if len(q) < 2:
        return []
    result = get_db().table("v_merchant_suggestions").select("*").ilike("name", f"{q}%").limit(8).execute()
    return result.data
