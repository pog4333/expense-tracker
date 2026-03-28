from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db
import pandas as pd
import uuid, io, json, zipfile

router = APIRouter(prefix="/backup")
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def backup_page(request: Request):
    db  = get_db()
    hid = request.state.user["household_id"]
    batches = (
        db.table("import_batches")
        .select("*,profiles(display_name)")
        .eq("household_id", hid)
        .order("started_at", desc=True)
        .limit(20)
        .execute()
    )
    return templates.TemplateResponse("backup/index.html", {
        "request": request, "user": request.state.user,
        "batches": batches.data,
    })


@router.post("/import")
@login_required
async def import_csv(request: Request, file: UploadFile = File(...)):
    db       = get_db()
    user     = request.state.user
    hid      = user["household_id"]
    batch_id = str(uuid.uuid4())

    db.table("import_batches").insert({
        "id": batch_id,
        "imported_by": user["user_id"],
        "filename": file.filename,
        "status": "pending",
        "household_id": hid,
    }).execute()

    try:
        contents = await file.read()
        buf = io.BytesIO(contents)

        if not zipfile.is_zipfile(buf):
            raise ValueError("Uploaded file is not a valid .zip archive")

        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            for required in ["transactions.csv", "accounts.csv", "buckets.csv"]:
                if required not in names:
                    raise ValueError(f"Missing {required} in zip")

            tx_df  = pd.read_csv(io.BytesIO(zf.read("transactions.csv")))
            acc_df = pd.read_csv(io.BytesIO(zf.read("accounts.csv")))
            bkt_df = pd.read_csv(io.BytesIO(zf.read("buckets.csv")))

        required_tx_cols = {"id", "type", "date", "merchant_name", "amount"}
        missing = required_tx_cols - set(tx_df.columns)
        if missing:
            raise ValueError(f"transactions.csv missing columns: {missing}")

        def df_to_records(df):
            return df.where(pd.notnull(df), None).to_dict(orient="records")

        db.rpc("import_from_csv", {
            "p_batch_id":     batch_id,
            "p_imported_by":  user["user_id"],
            "p_accounts":     json.dumps(df_to_records(acc_df)),
            "p_buckets":      json.dumps(df_to_records(bkt_df)),
            "p_transactions": json.dumps(df_to_records(tx_df)),
        }).execute()

        return RedirectResponse(url="/backup/?success=Import+completed+successfully", status_code=302)

    except Exception as e:
        db.table("import_batches").update({
            "status": "rolled_back",
            "error_detail": str(e),
        }).eq("id", batch_id).execute()
        return RedirectResponse(url=f"/backup/?error={str(e)[:200]}", status_code=302)
