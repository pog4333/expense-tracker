from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def dashboard(request: Request):
    db  = get_db()
    hid = request.state.user["household_id"]

    current_month   = db.rpc("get_current_month",       {"p_household_id": hid}).execute()
    pending_refunds = db.rpc("get_pending_refunds",     {"p_household_id": hid}).execute()
    budget_status   = db.rpc("get_budget_limit_status", {"p_household_id": hid}).execute()
    goals           = db.rpc("get_savings_goals",       {"p_household_id": hid}).execute()
    accounts        = db.table("accounts").select("*").eq("is_active", True).eq("household_id", hid).order("name").execute()
    balance_check   = db.rpc("get_balance_check", {}).execute()

    total_assets = sum(
        a["balance"] for a in accounts.data
        if a["type"] in ("checking", "savings", "debit_card")
    )
    total_cc_debt = sum(
        abs(a["balance"]) for a in accounts.data
        if a["type"] == "credit_card" and a["balance"] < 0
    )
    total_spent_month = sum(r["spent_this_month"] for r in current_month.data)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": request.state.user,
        "current_month": current_month.data,
        "accounts": accounts.data,
        "pending_refunds": pending_refunds.data,
        "budget_warnings": [b for b in budget_status.data if b["pct_used"] >= 80],
        "goals": [g for g in goals.data if not g["is_achieved"]],
        "total_assets": total_assets,
        "total_cc_debt": total_cc_debt,
        "total_spent_month": total_spent_month,
        "balance_check": balance_check.data[0] if balance_check.data else None,
        "is_balanced": balance_check.data[0]["is_balanced"] if balance_check.data else True,
    })
