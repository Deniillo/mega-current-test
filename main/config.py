import os

#Open router
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.environ["MODEL"]

# GitHub App
GITHUB_APP_ID = os.environ["GITHUB_APP_ID"]
GITHUB_PRIVATE_KEY_PATH = os.environ["GITHUB_PRIVATE_KEY_PATH"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

# YandexGPT
USE_YANDEX_GPT = os.environ.get("USE_YANDEX_GPT", "false").lower() == "true"
YANDEX_CLOUD_FOLDER = os.environ.get("YANDEX_CLOUD_FOLDER")
YANDEX_CLOUD_API_KEY = os.environ.get("YANDEX_CLOUD_API_KEY")
YANDEX_CLOUD_MODEL = os.environ.get("YANDEX_CLOUD_MODEL")