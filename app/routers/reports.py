from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db
import pandas as pd
import io, zipfile
from datetime import date

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def reports_page(request: Request):
    db  = get_db()
    hid = request.state.user["household_id"]

    monthly_cat   = db.rpc("get_monthly_by_category", {"p_household_id": hid}).execute()
    yoy           = db.rpc("get_year_over_year",       {"p_household_id": hid}).execute()
    subscriptions = db.rpc("get_subscriptions",        {"p_household_id": hid}).execute()
    forecast      = db.rpc("get_spending_forecast",    {"p_months_back": 6}).execute()
    daily         = db.table("transactions").select("date, amount").eq("type", "expense").eq("household_id", hid).gte("date", str(date.today().replace(day=1))).execute()

    return templates.TemplateResponse("reports/index.html", {
        "request": request, "user": request.state.user,
        "monthly_cat": monthly_cat.data,
        "yoy": yoy.data,
        "subscriptions": [s for s in subscriptions.data if s["likely_subscription"]],
        "forecast": forecast.data,
        "daily": daily.data,
    })


@router.get("/export/csv")
@login_required
async def export_csv(request: Request):
    db  = get_db()
    hid = request.state.user["household_id"]

    transactions = db.table("v_transactions").select("*").eq("household_id", hid).order("date", desc=True).execute()
    accounts     = db.table("accounts").select("*").eq("household_id", hid).execute()
    buckets      = db.table("buckets").select("*").eq("household_id", hid).execute()

    tx_df  = pd.DataFrame(transactions.data) if transactions.data else pd.DataFrame()
    acc_df = pd.DataFrame(accounts.data)     if accounts.data     else pd.DataFrame()
    bkt_df = pd.DataFrame(buckets.data)      if buckets.data      else pd.DataFrame()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("transactions.csv", tx_df.to_csv(index=False))
        zf.writestr("accounts.csv",     acc_df.to_csv(index=False))
        zf.writestr("buckets.csv",      bkt_df.to_csv(index=False))
    buf.seek(0)

    filename = f"expense-backup-{date.today().isoformat()}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/audit", response_class=HTMLResponse)
@login_required
async def audit_log(request: Request):
    db = get_db()
    logs = (
        db.table("audit_log")
        .select("*,profiles(display_name)")
        .order("changed_at", desc=True)
        .limit(200)
        .execute()
    )
    return templates.TemplateResponse("reports/audit.html", {
        "request": request, "user": request.state.user,
        "logs": logs.data,
    })
