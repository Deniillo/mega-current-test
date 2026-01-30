from fastapi import APIRouter, Header, HTTPException, Request
import hmac
import hashlib

from main.git.github_client import GitHubAppClient
from main.config import WEBHOOK_SECRET

router = APIRouter()

# Проверка подписи вебхука
def verify_signature(payload: bytes, signature: str) -> bool:
    mac = hmac.new(WEBHOOK_SECRET.encode(), msg=payload, digestmod=hashlib.sha256)
    return hmac.compare_digest(f"sha256={mac.hexdigest()}", signature)

# Вебхук endpoint
@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
):
    body = await request.body()

    if not x_hub_signature_256 or not verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    installation_id = payload["installation"]["id"]
    repo_full_name = payload["repository"]["full_name"]

    client = GitHubAppClient(installation_id)

    if x_github_event == "issues":
        issue_number = payload["issue"]["number"]
        client.get_issue(repo_full_name, issue_number).create_comment(":robot: issue увидел")
    elif x_github_event == "pull_request":
        pr_number = payload["pull_request"]["number"]
        client.add_pr_comment(repo_full_name, pr_number, ":robot: pr увидел")

    return {"status": "ok"}

# Ручка для теста комментария на issue
@router.post("/test_issue/")
async def test_issue(
    installation_id: int,
    repo_full_name: str,
    issue_number: int
):
    client = GitHubAppClient(installation_id)
    client.get_issue(repo_full_name, issue_number).create_comment(":robot:")
    return {"status": "Comment added"}