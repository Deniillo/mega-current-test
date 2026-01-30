import logging
from fastapi import APIRouter, Request, Header, HTTPException
import hmac, hashlib
from typing import List

from main.git.github_client import GitHubAppClient
from main.config import WEBHOOK_SECRET
from main.agents.coder_agent import run_coder_agent
from main.agents.reviewer_agent import run_reviewer_agent

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_signature(payload: bytes, signature: str) -> bool:
    """Проверка подписи GitHub webhook"""
    mac = hmac.new(WEBHOOK_SECRET.encode(), msg=payload, digestmod=hashlib.sha256)
    return hmac.compare_digest(f"sha256={mac.hexdigest()}", signature)


async def get_issue_comments(client: GitHubAppClient, repo_full_name: str, issue_number: int) -> List[str]:
    """Получение комментариев к issue"""
    comments = client.get_issue(repo_full_name, issue_number).get_comments()
    return [c.body for c in comments]


async def get_pr_diff(client: GitHubAppClient, repo_full_name: str, pr_number: int) -> str:
    """Получение diff PR в формате текста"""
    pr = client.get_pull_request(repo_full_name, pr_number)
    import requests
    headers = {"Authorization": f"token {client.token}", "Accept": "application/vnd.github.v3.diff"}
    resp = requests.get(pr.url, headers=headers)
    return resp.text if resp.status_code == 200 else ""


async def get_ci_status(client: GitHubAppClient, repo_full_name: str, pr_number: int) -> str:
    """
    Получение статуса CI для PR.
    Возможные значения:
      - "success" — все проверки прошли
      - "failure" — хотя бы одна проверка провалена
      - "pending" — проверки ещё выполняются
      - "no_ci" — CI не запущен или отсутствует
    """
    pr = client.get_pull_request(repo_full_name, pr_number)
    commits = pr.get_commits()
    if commits.totalCount == 0:
        return "no_ci"

    latest_commit = commits[-1]

    try:
        combined_status = latest_commit.get_combined_status()
    except AttributeError:
        return "no_ci"

    if combined_status.total_count == 0:
        return "no_ci"
    if any(s.state == "failure" for s in combined_status.statuses):
        return "failure"
    if all(s.state == "success" for s in combined_status.statuses):
        return "success"
    return "pending"


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
):
    body = await request.body()
    if not x_hub_signature_256 or not verify_signature(body, x_hub_signature_256):
        logger.warning("Invalid or missing signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    if x_github_event == "ping":
        return {"status": "pong"}

    try:
        installation_id = payload["installation"]["id"]
        repo_full_name = payload["repository"]["full_name"]
    except KeyError:
        logger.exception("Malformed payload")
        raise HTTPException(status_code=400, detail="Malformed payload")

    client = GitHubAppClient(installation_id)

    # --- Coder Agent: обработка новых issue ---
    if x_github_event == "issues" and payload.get("action") == "opened":
        issue_number = payload["issue"]["number"]
        issue_title = payload["issue"]["title"]
        issue_body = payload["issue"].get("body", "")
        comments = await get_issue_comments(client, repo_full_name, issue_number)
        agent_response = await run_coder_agent(issue_title, issue_body, comments)
        logger.info("Coder Agent response: %s", agent_response)

        branch_name = f"issue-{issue_number}-fix"

        client.create_branch(repo_full_name, branch_name)

        client.create_or_update_file(
            repo_full_name,
            branch_name,
            "README.md",
            f"# Изменение по issue #{issue_number}\n\n{agent_response}",
            f"Issue #{issue_number} fix via Coder Agent"
        )

        client.create_pull_request(
            repo_full_name,
            f"Fix for issue #{issue_number}",
            branch_name,
            "main",
            body=agent_response
        )
        return {"status": "coder agent completed"}

    # --- Reviewer Agent: обработка новых PR ---
    elif x_github_event == "pull_request" and payload.get("action") == "opened":
        pr_number = payload["pull_request"]["number"]
        pr_title = payload["pull_request"]["title"]
        pr_body = payload["pull_request"].get("body", "")

        diff_text = await get_pr_diff(client, repo_full_name, pr_number)
        ci_status = await get_ci_status(client, repo_full_name, pr_number)

        if ci_status == "no_ci":
            # Если CI тестов нет, пишем предупреждающий комментарий
            client.add_pr_comment(repo_full_name, pr_number, "⚠️ CI тестов не было для этого PR.")
        else:
            review_comment = await run_reviewer_agent(pr_title, pr_body, diff_text, ci_status)
            client.add_pr_comment(repo_full_name, pr_number, review_comment)

        return {"status": "reviewer agent completed"}

    logger.info("Unhandled event type: %s", x_github_event)
    return {"status": "ok"}