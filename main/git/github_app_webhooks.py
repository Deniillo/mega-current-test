from fastapi import APIRouter, Header, HTTPException, Request
import hmac
import hashlib
import logging

from main.git.github_client import GitHubAppClient
from main.config import WEBHOOK_SECRET

logger = logging.getLogger(__name__)

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
    logger.info("Webhook received")
    logger.debug("Headers: x_github_event=%s, x_hub_signature_256=%s",
                 x_github_event, x_hub_signature_256)

    body = await request.body()
    logger.debug("Raw body size=%d bytes", len(body))

    if not x_hub_signature_256:
        logger.warning("Missing X-Hub-Signature-256 header")
        raise HTTPException(status_code=400, detail="Missing signature")

    if not verify_signature(body, x_hub_signature_256):
        logger.error("Invalid webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    logger.debug("Payload keys: %s", payload.keys())

    if x_github_event == "ping":
        logger.info("Ping event received")
        return {"status": "pong"}

    try:
        installation_id = payload["installation"]["id"]
        repo_full_name = payload["repository"]["full_name"]
    except KeyError:
        logger.exception("Malformed payload")
        raise HTTPException(status_code=400, detail="Malformed payload")

    logger.info(
        "Event=%s repo=%s installation_id=%s",
        x_github_event,
        repo_full_name,
        installation_id,
    )

    client = GitHubAppClient(installation_id)

    if x_github_event == "issues":
        issue_number = payload["issue"]["number"]
        logger.info("Issue event: #%s", issue_number)

        client.get_issue(repo_full_name, issue_number).create_comment(
            ":robot: issue увидел"
        )

        logger.info("Comment added to issue #%s", issue_number)

    elif x_github_event == "pull_request":
        pr_number = payload["pull_request"]["number"]
        logger.info("Pull request event: #%s", pr_number)

        client.add_pr_comment(
            repo_full_name,
            pr_number,
            ":robot: pr увидел"
        )

        logger.info("Comment added to PR #%s", pr_number)

    else:
        logger.warning("Unhandled event type: %s", x_github_event)

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