from fastapi import FastAPI
from main.git.github_app_webhooks import router as github_webhooks_router

# Главный объект FastAPI
app = FastAPI(title="GitHub App Client API")

# Подключаем ручки из github_webhooks
app.include_router(github_webhooks_router)