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
    mac = hmac.new(WEBHOOK_SECRET.encode(), msg=payload, digestmod=hashlib.sha256)
    return hmac.compare_digest(f"sha256={mac.hexdigest()}", signature)


async def get_issue_comments(client: GitHubAppClient, repo_full_name: str, issue_number: int) -> List[str]:
    comments = client.get_issue(repo_full_name, issue_number).get_comments()
    return [c.body for c in comments]


async def get_pr_diff(client: GitHubAppClient, repo_full_name: str, pr_number: int) -> str:
    pr = client.get_pull_request(repo_full_name, pr_number)
    import requests
    headers = {"Authorization": f"token {client.token}", "Accept": "application/vnd.github.v3.diff"}
    resp = requests.get(pr.url, headers=headers)
    return resp.text if resp.status_code == 200 else ""


async def get_ci_status(client: GitHubAppClient, repo_full_name: str, pr_number: int) -> str:
    pr = client.get_pull_request(repo_full_name, pr_number)
    statuses = pr.get_combined_status()
    if statuses.total_count == 0:
        return "pending"
    if any(s.state == "failure" for s in statuses.statuses):
        return "failure"
    if all(s.state == "success" for s in statuses.statuses):
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

    # Coder Agent
    if x_github_event == "issues" and payload.get("action") == "opened":
        issue_number = payload["issue"]["number"]
        issue_title = payload["issue"]["title"]
        issue_body = payload["issue"].get("body", "")
        comments = await get_issue_comments(client, repo_full_name, issue_number)
        agent_response = await run_coder_agent(issue_title, issue_body, comments)
        logger.info("Coder Agent response: %s", agent_response)

        branch_name = f"issue-{issue_number}-fix"
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

    # Reviewer Agent
    elif x_github_event == "pull_request" and payload.get("action") == "opened":
        pr_number = payload["pull_request"]["number"]
        pr_title = payload["pull_request"]["title"]
        pr_body = payload["pull_request"].get("body", "")

        diff_text = await get_pr_diff(client, repo_full_name, pr_number)
        ci_status = await get_ci_status(client, repo_full_name, pr_number)

        review_comment = await run_reviewer_agent(pr_title, pr_body, diff_text, ci_status)
        logger.info("Reviewer Agent response: %s", review_comment)

        client.add_pr_comment(repo_full_name, pr_number, review_comment)
        return {"status": "reviewer agent completed"}

    logger.info("Unhandled event type: %s", x_github_event)
    return {"status": "ok"}