from fastapi import FastAPI
from main.git.github_app_webhooks import router as github_webhooks_router
from main.logging import setup_logging

setup_logging()
app = FastAPI(title="GitHub App Client API")

app.include_router(github_webhooks_router)