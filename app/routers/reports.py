from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db
import pandas as pd
import io

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def reports_page(request: Request):
    db = get_db()
    monthly_cat  = db.table("v_monthly_by_category").select("*").order("month", desc=True).limit(120).execute()
    yoy          = db.table("v_year_over_year").select("*").execute()
    subscriptions = db.table("v_subscriptions").select("*").eq("likely_subscription", True).execute()
    forecast     = db.rpc("get_spending_forecast", {"p_months_back": 6}).execute()
    daily        = db.table("v_daily_spending").select("*").execute()

    return templates.TemplateResponse("reports/index.html", {
        "request": request, "user": request.state.user,
        "monthly_cat": monthly_cat.data,
        "yoy": yoy.data,
        "subscriptions": subscriptions.data,
        "forecast": forecast.data,
        "daily": daily.data,
    })


@router.get("/export/csv")
@login_required
async def export_csv(request: Request):
    """Export all transactions as CSV for backup."""
    db = get_db()

    # Fetch all data
    transactions = db.table("v_transactions").select("*").order("date", desc=True).execute()
    accounts     = db.table("accounts").select("*").execute()
    buckets      = db.table("buckets").select("*").execute()

    # Build multi-sheet CSV as a zip of CSVs
    tx_df  = pd.DataFrame(transactions.data)
    acc_df = pd.DataFrame(accounts.data)
    bkt_df = pd.DataFrame(buckets.data)

    # Create a zip in memory
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("transactions.csv", tx_df.to_csv(index=False))
        zf.writestr("accounts.csv",     acc_df.to_csv(index=False))
        zf.writestr("buckets.csv",       bkt_df.to_csv(index=False))
    buf.seek(0)

    from datetime import date
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
