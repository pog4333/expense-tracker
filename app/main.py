from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routers import auth_routes, dashboard, transactions, accounts, reports, backup
from app.config import DEBUG

app = FastAPI(title="Expense Tracker", debug=DEBUG)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_routes.router)
app.include_router(dashboard.router)
app.include_router(transactions.router)
app.include_router(accounts.router)
app.include_router(reports.router)
app.include_router(backup.router)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("errors/404.html", {"request": request}, status_code=404)

@app.exception_handler(500)
async def server_error(request: Request, exc):
    return templates.TemplateResponse("errors/500.html", {"request": request}, status_code=500)
