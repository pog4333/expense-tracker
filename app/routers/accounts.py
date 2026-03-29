from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db
from decimal import Decimal

router = APIRouter(prefix="/accounts")
templates = Jinja2Templates(directory="app/templates")
ACCOUNT_TYPES = ["checking", "savings", "credit_card", "debit_card"]


@router.get("/", response_class=HTMLResponse)
@login_required
async def accounts_page(request: Request):
    db  = get_db()
    hid = request.state.user["household_id"]

    accounts = db.table("accounts").select("*").eq("household_id", hid).order("name").execute()
    buckets  = db.table("buckets").select("*").eq("household_id", hid).order("sort_order").execute()
    goals = db.rpc("get_savings_goals", {"p_household_id": hid}).execute().data
    balance  = db.rpc("get_balance_check", {}).execute()

    # Build allocation list: all active buckets for this household
    all_buckets_r  = db.table("buckets").select("id,name").eq("is_active", True).eq("household_id", hid).order("sort_order").execute()
    existing_alloc = db.table("allocation_rules").select("*").eq("household_id", hid).execute()
    alloc_map  = {a["bucket_id"]: a["percentage"] for a in existing_alloc.data}
    alloc_data = [
        {"bucket_id": b["id"], "percentage": alloc_map.get(b["id"], 0), "buckets": {"name": b["name"]}}
        for b in all_buckets_r.data
    ]

    # Transaction counts for delete safety
    acc_tx_counts = {}
    for a in accounts.data:
        r = db.table("transactions").select("id", count="exact").eq("account_id", a["id"]).eq("household_id", hid).execute()
        acc_tx_counts[a["id"]] = r.count or 0

    bkt_tx_counts = {}
    for b in buckets.data:
        r = db.table("transactions").select("id", count="exact").eq("bucket_id", b["id"]).eq("household_id", hid).execute()
        bkt_tx_counts[b["id"]] = r.count or 0

    return templates.TemplateResponse("accounts/index.html", {
        "request": request, "user": request.state.user,
        "accounts": accounts.data, "buckets": buckets.data,
        "goals": goals, "allocations": alloc_data,
        "balance_check": balance.data[0] if balance.data else None,
        "account_types": ACCOUNT_TYPES,
        "acc_tx_counts": acc_tx_counts,
        "bkt_tx_counts": bkt_tx_counts,
    })


@router.post("/add")
@login_required
async def add_account(
    request: Request,
    name: str              = Form(...),
    type: str              = Form(...),
    initial_balance: str   = Form("0"),
    credit_limit: str      = Form(""),
    linked_account_id: str = Form(""),
):
    db  = get_db()
    hid = request.state.user["household_id"]
    bal = Decimal(initial_balance or "0")
    db.table("accounts").insert({
        "name": name.strip(), "type": type,
        "balance": str(bal), "initial_balance": str(bal),
        "credit_limit": str(Decimal(credit_limit)) if credit_limit else None,
        "linked_account_id": linked_account_id or None,
        "household_id": hid,
    }).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/{account_id}/edit")
@login_required
async def edit_account(
    request: Request, account_id: str,
    name: str         = Form(...),
    credit_limit: str = Form(""),
    is_active: bool   = Form(True),
):
    hid = request.state.user["household_id"]
    get_db().table("accounts").update({
        "name": name.strip(),
        "credit_limit": str(Decimal(credit_limit)) if credit_limit else None,
        "is_active": is_active,
    }).eq("id", account_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/buckets/add")
@login_required
async def add_bucket(request: Request, name: str = Form(...), balance: str = Form("0")):
    db  = get_db()
    hid = request.state.user["household_id"]
    existing = db.table("buckets").select("sort_order").eq("household_id", hid).order("sort_order", desc=True).limit(1).execute()
    next_order = (existing.data[0]["sort_order"] + 1) if existing.data else 1
    db.table("buckets").insert({
        "name": name.strip(),
        "balance": str(Decimal(balance or "0")),
        "sort_order": next_order,
        "household_id": hid,
    }).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/buckets/{bucket_id}/edit")
@login_required
async def edit_bucket(
    request: Request, bucket_id: str,
    name: str       = Form(...),
    is_active: bool = Form(True),
):
    hid = request.state.user["household_id"]
    get_db().table("buckets").update({"name": name.strip(), "is_active": is_active}).eq("id", bucket_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/allocations/save")
@login_required
async def save_allocations(request: Request):
    db   = get_db()
    hid  = request.state.user["household_id"]
    form = await request.form()
    bucket_ids  = form.getlist("bucket_id")
    percentages = form.getlist("percentage")
    total = sum(Decimal(p) for p in percentages)
    if total != Decimal("100"):
        return RedirectResponse(url=f"/accounts/?error=Allocations+must+sum+to+100+%28got+{total}%25%29", status_code=302)
    # Delete existing rules for this household only
    db.table("allocation_rules").delete().eq("household_id", hid).execute()
    rules = [
        {"bucket_id": bid, "percentage": str(Decimal(pct)), "household_id": hid}
        for bid, pct in zip(bucket_ids, percentages) if Decimal(pct) > 0
    ]
    if rules:
        db.table("allocation_rules").insert(rules).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/goals/add")
@login_required
async def add_goal(
    request: Request,
    bucket_id: str     = Form(...),
    name: str          = Form(...),
    target_amount: str = Form(...),
    target_date: str   = Form(""),
):
    hid = request.state.user["household_id"]
    get_db().table("savings_goals").insert({
        "bucket_id": bucket_id, "name": name.strip(),
        "target_amount": str(Decimal(target_amount)),
        "target_date": target_date or None,
        "household_id": hid,
    }).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/goals/{goal_id}/achieve")
@login_required
async def mark_goal_achieved(request: Request, goal_id: str):
    hid = request.state.user["household_id"]
    get_db().table("savings_goals").update({"is_achieved": True}).eq("id", goal_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/{account_id}/deactivate")
@login_required
async def deactivate_account(request: Request, account_id: str):
    hid = request.state.user["household_id"]
    get_db().table("accounts").update({"is_active": False}).eq("id", account_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/{account_id}/reactivate")
@login_required
async def reactivate_account(request: Request, account_id: str):
    hid = request.state.user["household_id"]
    get_db().table("accounts").update({"is_active": True}).eq("id", account_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/{account_id}/delete")
@login_required
async def delete_account(request: Request, account_id: str):
    db  = get_db()
    hid = request.state.user["household_id"]
    tx  = db.table("transactions").select("id").eq("account_id", account_id).eq("household_id", hid).limit(1).execute()
    if tx.data:
        return RedirectResponse(url="/accounts/?error=Cannot+delete+account+with+transactions", status_code=302)
    acc = db.table("accounts").select("balance").eq("id", account_id).eq("household_id", hid).single().execute()
    if acc.data and float(acc.data["balance"]) != 0:
        return RedirectResponse(url="/accounts/?error=Cannot+delete+account+with+non-zero+balance", status_code=302)
    db.table("accounts").delete().eq("id", account_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/buckets/{bucket_id}/deactivate")
@login_required
async def deactivate_bucket(request: Request, bucket_id: str):
    hid = request.state.user["household_id"]
    get_db().table("buckets").update({"is_active": False}).eq("id", bucket_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/buckets/{bucket_id}/reactivate")
@login_required
async def reactivate_bucket(request: Request, bucket_id: str):
    hid = request.state.user["household_id"]
    get_db().table("buckets").update({"is_active": True}).eq("id", bucket_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)


@router.post("/buckets/{bucket_id}/delete")
@login_required
async def delete_bucket(request: Request, bucket_id: str):
    db  = get_db()
    hid = request.state.user["household_id"]
    tx  = db.table("transactions").select("id").eq("bucket_id", bucket_id).eq("household_id", hid).limit(1).execute()
    if tx.data:
        return RedirectResponse(url="/accounts/?error=Cannot+delete+bucket+with+transactions", status_code=302)
    bkt = db.table("buckets").select("balance").eq("id", bucket_id).eq("household_id", hid).single().execute()
    if bkt.data and float(bkt.data["balance"]) != 0:
        return RedirectResponse(url="/accounts/?error=Cannot+delete+bucket+with+non-zero+balance", status_code=302)
    db.table("buckets").delete().eq("id", bucket_id).eq("household_id", hid).execute()
    return RedirectResponse(url="/accounts/", status_code=302)
