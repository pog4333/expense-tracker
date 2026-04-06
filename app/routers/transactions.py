from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db
from decimal import Decimal, InvalidOperation
from typing import Optional

router = APIRouter(prefix="/transactions")
templates = Jinja2Templates(directory="app/templates")


def _get_form_data(db, household_id: str):
    accounts = db.table("accounts").select("id,name,type") \
        .eq("is_active", True).eq("household_id", household_id).order("name").execute()
    buckets = db.table("buckets").select("id,name") \
        .eq("is_active", True).eq("household_id", household_id).order("sort_order").execute()
    all_cats = db.table("categories").select("id,name,parent_id") \
        .eq("household_id", household_id).order("sort_order").execute()
    if not all_cats.data:
        all_cats = db.table("categories").select("id,name,parent_id").order("sort_order").execute()
    parents  = [c for c in all_cats.data if c["parent_id"] is None]
    children = [c for c in all_cats.data if c["parent_id"] is not None]
    for p in parents:
        p["subcategories"] = [c for c in children if c["parent_id"] == p["id"]]
    return accounts.data, buckets.data, parents


def _insert_split_transaction(db, base_data: dict, splits: list[dict]) -> str:
    """
    Insert a parent split transaction and its children.
    base_data: common fields (date, merchant_name, amount, account_id, etc.)
    splits: list of {bucket_id, amount, category_id, note}
    Returns parent transaction id.
    """
    import uuid

    # Validate splits sum to total
    total = Decimal(str(base_data["amount"]))
    split_total = sum(Decimal(str(s["amount"])) for s in splits)
    if abs(split_total - total) > Decimal("0.01"):
        raise ValueError(f"Split amounts ({split_total}) must equal total ({total})")

    # Insert parent (type=split, no bucket)
    parent_data = {**base_data, "type": "split", "bucket_id": None, "category_id": None}
    parent = db.table("transactions").insert(parent_data).execute()
    parent_id = parent.data[0]["id"]

    # Insert children
    children = []
    for s in splits:
        children.append({
            **base_data,
            "type": base_data.get("income_type", "expense"),
            "amount": str(Decimal(str(s["amount"]))),
            "bucket_id": s["bucket_id"],
            "category_id": s.get("category_id") or None,
            "note": s.get("note") or base_data.get("note"),
            "split_parent_id": parent_id,
            "is_salary": False,
        })
    db.table("transactions").insert(children).execute()
    return parent_id


# ── Transaction list with filters ─────────────────────────────

@router.get("/", response_class=HTMLResponse)
@login_required
async def transaction_list(request: Request):
    db  = get_db()
    hid = request.state.user["household_id"]

    # Read filter params
    filter_account  = request.query_params.get("account", "")
    filter_bucket   = request.query_params.get("bucket", "")
    filter_category = request.query_params.get("category", "")
    filter_type     = request.query_params.get("type", "")

    query = db.table("v_transactions").select("*") \
        .eq("household_id", hid) \
        .is_("split_parent_id", None) \
        .order("date", desc=True) \
        .limit(200)

    if filter_account:
        query = query.eq("account_id", filter_account)
    if filter_bucket:
        query = query.eq("bucket_id", filter_bucket)
    if filter_category:
        query = query.eq("category_id", filter_category)
    if filter_type:
        query = query.eq("type", filter_type)

    result = query.execute()

    # Load filter options
    accounts   = db.table("accounts").select("id,name").eq("household_id", hid).eq("is_active", True).order("name").execute()
    buckets    = db.table("buckets").select("id,name").eq("household_id", hid).eq("is_active", True).order("sort_order").execute()
    all_cats   = db.table("categories").select("id,name,parent_id").eq("household_id", hid).order("sort_order").execute()
    categories = [c for c in all_cats.data if c["parent_id"] is not None]

    return templates.TemplateResponse("transactions/list.html", {
        "request": request, "user": request.state.user,
        "transactions": result.data,
        "accounts": accounts.data,
        "buckets": buckets.data,
        "categories": categories,
        "filter_account": filter_account,
        "filter_bucket": filter_bucket,
        "filter_category": filter_category,
        "filter_type": filter_type,
    })


# ── Add transaction ────────────────────────────────────────────

@router.get("/add", response_class=HTMLResponse)
@login_required
async def add_transaction_page(request: Request, merchant: str = ""):
    db  = get_db()
    hid = request.state.user["household_id"]
    accounts, buckets, categories = _get_form_data(db, hid)
    autofill = None
    if merchant:
        try:
            m = db.table("v_merchant_suggestions").select("*") \
                .eq("household_id", hid).ilike("name", merchant).limit(1).execute()
            autofill = m.data[0] if m.data else None
        except Exception:
            autofill = None
    return templates.TemplateResponse("transactions/add.html", {
        "request": request, "user": request.state.user,
        "accounts": accounts, "buckets": buckets,
        "categories": categories, "autofill": autofill,
        "merchant_query": merchant,
    })


@router.post("/add")
@login_required
async def add_transaction(request: Request):
    """
    Handles both simple and split transactions.
    Split is detected by presence of multiple bucket_id values in the form.
    Also handles manual income allocation (same split mechanism, type=income).
    """
    db   = get_db()
    user = request.state.user
    hid  = user["household_id"]
    form = await request.form()

    date          = form.get("date")
    merchant_name = form.get("merchant_name", "").strip()
    amount        = form.get("amount")
    account_id    = form.get("account_id")
    note          = form.get("note", "").strip() or None
    is_salary     = form.get("is_salary") == "true"
    tx_type       = form.get("tx_type", "expense")  # expense / income

    # Split fields — multiple values
    bucket_ids    = form.getlist("bucket_id")
    split_amounts = form.getlist("split_amount")
    category_ids  = form.getlist("category_id")
    split_notes   = form.getlist("split_note")

    base_data = {
        "date": date,
        "merchant_name": merchant_name,
        "amount": str(Decimal(amount)),
        "account_id": account_id,
        "note": note,
        "entered_by": user["user_id"],
        "household_id": hid,
        "is_salary": is_salary,
    }

    # Determine if this is a split (multiple buckets) or simple
    is_split = len(bucket_ids) > 1 or (len(bucket_ids) == 1 and split_amounts)

    if is_split:
        splits = []
        for i, bid in enumerate(bucket_ids):
            splits.append({
                "bucket_id": bid,
                "amount": split_amounts[i] if i < len(split_amounts) else 0,
                "category_id": category_ids[i] if i < len(category_ids) else None,
                "note": split_notes[i] if i < len(split_notes) else None,
            })
        base_data["income_type"] = tx_type  # passed through to children
        try:
            _insert_split_transaction(db, base_data, splits)
        except ValueError as e:
            accounts, buckets, categories = _get_form_data(db, hid)
            return templates.TemplateResponse("transactions/add.html", {
                "request": request, "user": request.state.user,
                "accounts": accounts, "buckets": buckets,
                "categories": categories, "autofill": None,
                "merchant_query": merchant_name,
                "error": str(e),
            })
    else:
        # Simple single-bucket transaction
        tx_data = {
            **base_data,
            "type": "income" if (tx_type == "income" or is_salary) else "expense",
            "bucket_id": bucket_ids[0] if bucket_ids else None,
            "category_id": category_ids[0] if category_ids else None,
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


# ── Edit ──────────────────────────────────────────────────────

@router.get("/{tx_id}/edit", response_class=HTMLResponse)
@login_required
async def edit_transaction_page(request: Request, tx_id: str):
    db  = get_db()
    hid = request.state.user["household_id"]
    result = db.table("v_transactions").select("*") \
        .eq("id", tx_id).eq("household_id", hid).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Not found")
    accounts, buckets, categories = _get_form_data(db, hid)
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
    bucket_id: str     = Form(""),
    category_id: str   = Form(""),
    note: str          = Form(""),
):
    db  = get_db()
    hid = request.state.user["household_id"]
    db.table("transactions").update({
        "date": date,
        "merchant_name": merchant_name.strip(),
        "amount": str(Decimal(amount)),
        "account_id": account_id,
        "bucket_id": bucket_id or None,
        "category_id": category_id or None,
        "note": note.strip() or None,
    }).eq("id", tx_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


# ── Delete ────────────────────────────────────────────────────

@router.post("/{tx_id}/delete")
@login_required
async def delete_transaction(request: Request, tx_id: str):
    hid = request.state.user["household_id"]
    get_db().table("transactions").delete() \
        .eq("id", tx_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


# ── Refund ────────────────────────────────────────────────────

@router.post("/{tx_id}/refund/request")
@login_required
async def request_refund(request: Request, tx_id: str):
    hid = request.state.user["household_id"]
    get_db().table("transactions").update({"refund_status": "pending"}) \
        .eq("id", tx_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


@router.post("/{tx_id}/refund/confirm")
@login_required
async def confirm_refund(
    request: Request, tx_id: str,
    date: str   = Form(...),
    amount: str = Form(...),
):
    db   = get_db()
    hid  = request.state.user["household_id"]
    orig = db.table("transactions").select("*") \
        .eq("id", tx_id).eq("household_id", hid).single().execute().data
    if not orig:
        raise HTTPException(status_code=404, detail="Not found")
    db.table("transactions").insert({
        "type": "income",
        "date": date,
        "merchant_name": f"Refund – {orig['merchant_name']}",
        "amount": str(Decimal(amount)),
        "account_id": orig["account_id"],
        "bucket_id": orig["bucket_id"],   # back to original bucket
        "category_id": orig["category_id"],
        "refund_of_id": tx_id,
        "note": "Refund confirmed",
        "entered_by": request.state.user["user_id"],
        "household_id": hid,
    }).execute()
    db.table("transactions").update({"refund_status": "confirmed"}) \
        .eq("id", tx_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


# ── Transfer ──────────────────────────────────────────────────

@router.get("/transfer", response_class=HTMLResponse)
@login_required
async def transfer_page(request: Request):
    db  = get_db()
    hid = request.state.user["household_id"]
    accounts = db.table("accounts").select("id,name,type") \
        .eq("is_active", True).eq("household_id", hid).order("name").execute()
    buckets = db.table("buckets").select("id,name") \
        .eq("is_active", True).eq("household_id", hid).order("sort_order").execute()
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
    db  = get_db()
    hid = request.state.user["household_id"]
    tx_data = {
        "type": "transfer",
        "transfer_type": transfer_type,
        "date": date,
        "merchant_name": "Transfer",
        "amount": str(Decimal(amount)),
        "note": note.strip() or None,
        "entered_by": request.state.user["user_id"],
        "household_id": hid,
    }
    if transfer_type in ("account", "cc_payment"):
        tx_data["from_account_id"] = from_id
        tx_data["to_account_id"]   = to_id
    else:
        tx_data["from_bucket_id"] = from_id
        tx_data["to_bucket_id"]   = to_id
    db.table("transactions").insert(tx_data).execute()
    return RedirectResponse(url="/transactions/", status_code=302)


# ── Merchant autocomplete ─────────────────────────────────────

@router.get("/merchant-suggest")
@login_required
async def merchant_suggest(request: Request, q: str = ""):
    if len(q) < 2:
        return []
    hid = request.state.user["household_id"]
    try:
        result = get_db().table("v_merchant_suggestions").select("*") \
            .eq("household_id", hid).ilike("name", f"{q}%").limit(8).execute()
        return result.data
    except Exception:
        return []
