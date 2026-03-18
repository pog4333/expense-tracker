from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.auth import login_required
from app.database import get_db
import pandas as pd
import uuid, io

router = APIRouter(prefix="/backup")
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def backup_page(request: Request):
    db = get_db()
    batches = (
        db.table("import_batches")
        .select("*,profiles(display_name)")
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
    """
    All-or-nothing CSV restore.
    Expects a .zip containing transactions.csv, accounts.csv, buckets.csv
    (same format as the export).
    """
    db      = get_db()
    user    = request.state.user
    batch_id = str(uuid.uuid4())

    # Register the batch attempt
    db.table("import_batches").insert({
        "id": batch_id,
        "imported_by": user["user_id"],
        "filename": file.filename,
        "status": "pending",
    }).execute()

    try:
        import zipfile
        contents = await file.read()
        buf = io.BytesIO(contents)

        if not zipfile.is_zipfile(buf):
            raise ValueError("Uploaded file is not a valid .zip archive")

        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            if "transactions.csv" not in names:
                raise ValueError("Missing transactions.csv in zip")
            if "accounts.csv" not in names:
                raise ValueError("Missing accounts.csv in zip")
            if "buckets.csv" not in names:
                raise ValueError("Missing buckets.csv in zip")

            tx_df  = pd.read_csv(io.BytesIO(zf.read("transactions.csv")))
            acc_df = pd.read_csv(io.BytesIO(zf.read("accounts.csv")))
            bkt_df = pd.read_csv(io.BytesIO(zf.read("buckets.csv")))

        # Validate required columns
        required_tx_cols = {"id", "type", "date", "merchant_name", "amount"}
        missing = required_tx_cols - set(tx_df.columns)
        if missing:
            raise ValueError(f"transactions.csv missing columns: {missing}")

        # Convert DataFrames to JSON-serialisable dicts, replacing NaN with None
        def df_to_records(df):
            return df.where(pd.notnull(df), None).to_dict(orient="records")

        import json
        result = db.rpc("import_from_csv", {
            "p_batch_id":      batch_id,
            "p_imported_by":   user["user_id"],
            "p_accounts":      json.dumps(df_to_records(acc_df)),
            "p_buckets":       json.dumps(df_to_records(bkt_df)),
            "p_transactions":  json.dumps(df_to_records(tx_df)),
        }).execute()

        return RedirectResponse(
            url="/backup/?success=Import+completed+successfully",
            status_code=302
        )

    except Exception as e:
        # Mark batch as failed
        db.table("import_batches").update({
            "status": "rolled_back",
            "error_detail": str(e),
        }).eq("id", batch_id).execute()

        return RedirectResponse(
            url=f"/backup/?error={str(e)[:200]}",
            status_code=302
        )
