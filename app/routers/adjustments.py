from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from app.auth import login_required
from app.database import get_db
from decimal import Decimal
from datetime import date

router = APIRouter(prefix="/accounts")


@router.post("/{account_id}/adjust")
@login_required
async def adjust_account_balance(
    request: Request,
    account_id: str,
    new_balance: str = Form(...),
    reason: str      = Form(...),
    confirmed: bool  = Form(False),
):
    db   = get_db()
    user = request.state.user
    hid  = user["household_id"]

    if not confirmed:
        return RedirectResponse(url="/accounts/?error=Please+confirm+the+adjustment", status_code=302)
    if not reason.strip():
        return RedirectResponse(url="/accounts/?error=A+reason+is+required+for+balance+adjustments", status_code=302)

    account = db.table("accounts").select("balance,name").eq("id", account_id).eq("household_id", hid).single().execute()
    if not account.data:
        raise HTTPException(status_code=404, detail="Account not found")

    current = Decimal(str(account.data["balance"]))
    target  = Decimal(new_balance)
    diff    = target - current

    if diff == 0:
        return RedirectResponse(url="/accounts/?error=New+balance+is+same+as+current", status_code=302)

    db.table("accounts").update({"balance": str(target)}).eq("id", account_id).eq("household_id", hid).execute()

    db.table("transactions").insert({
        "type": "adjustment",
        "date": date.today().isoformat(),
        "merchant_name": f"Balance adjustment — {account.data['name']}",
        "amount": str(abs(diff)),
        "account_id": account_id,
        "bucket_id": None,
        "note": f"Manual adjustment: ${current} → ${target}. Reason: {reason.strip()}",
        "entered_by": user["user_id"],
        "household_id": hid,
    }).execute()

    return RedirectResponse(url="/accounts/?success=Balance+adjusted+successfully", status_code=302)


@router.post("/buckets/{bucket_id}/adjust")
@login_required
async def adjust_bucket_balance(
    request: Request,
    bucket_id: str,
    new_balance: str = Form(...),
    reason: str      = Form(...),
    confirmed: bool  = Form(False),
):
    db   = get_db()
    user = request.state.user
    hid  = user["household_id"]

    if not confirmed:
        return RedirectResponse(url="/accounts/?error=Please+confirm+the+adjustment", status_code=302)
    if not reason.strip():
        return RedirectResponse(url="/accounts/?error=A+reason+is+required", status_code=302)

    bucket = db.table("buckets").select("balance,name").eq("id", bucket_id).eq("household_id", hid).single().execute()
    if not bucket.data:
        raise HTTPException(status_code=404, detail="Bucket not found")

    current = Decimal(str(bucket.data["balance"]))
    target  = Decimal(new_balance)
    diff    = target - current

    if diff == 0:
        return RedirectResponse(url="/accounts/?error=New+balance+is+same+as+current", status_code=302)

    db.table("buckets").update({"balance": str(target)}).eq("id", bucket_id).eq("household_id", hid).execute()

    db.table("transactions").insert({
        "type": "adjustment",
        "date": date.today().isoformat(),
        "merchant_name": f"Bucket adjustment — {bucket.data['name']}",
        "amount": str(abs(diff)),
        "account_id": None,
        "bucket_id": bucket_id,
        "note": f"Manual adjustment: ${current} → ${target}. Reason: {reason.strip()}",
        "entered_by": user["user_id"],
        "household_id": hid,
    }).execute()

    return RedirectResponse(url="/accounts/?success=Bucket+balance+adjusted", status_code=302)
