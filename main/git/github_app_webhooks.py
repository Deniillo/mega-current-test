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
    pr = client.get_pull_request(repo_full_name, pr_number)
    commits = pr.get_commits()

    latest_commit = None
    for commit in commits:
        latest_commit = commit
    if latest_commit is None:
        return "no_ci"

    statuses = latest_commit.get_statuses()
    if statuses.totalCount == 0:
        return "no_ci"

    states = [s.state for s in statuses]
    if "failure" in states:
        return "failure"
    if all(s == "success" for s in states):
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

        repo_files = client.list_files(repo_full_name)

        allowed_files = []
        files_context = []
        for path in repo_files:
            logger.info("обрабатываю файл %s", path)
            content = client.get_file_content(repo_full_name, path, ref="main")
            if content is not None:
                logger.info("добавил файл %s", path)
                allowed_files.append(path)
                files_context.append(f"=== {path} ===\n{content}")
            # else:
            #     logger.info("не сумел обработать файл %s", path)

        context = (
                f"Issue: {issue_title}\n"
                f"Описание: {issue_body}\n"
                f"Комментарии:\n" + "\n".join(comments) + "\n\n" +
                "Содержимое файлов репозитория:\n" + "\n\n".join(files_context)
        )

        logger.info(context)

        files_to_update = await run_coder_agent(context, allowed_files=repo_files)
        logger.info("Files to update: %s", list(files_to_update.keys()))

        branch_name = f"issue-{issue_number}-fix"
        client.create_branch(repo_full_name, branch_name)

        for path, content in files_to_update.items():
            client.create_or_update_file(
                repo_full_name,
                branch_name,
                path,
                content,
                f"Issue #{issue_number} fix via Coder Agent"
            )

        client.create_pull_request(
            repo_full_name,
            f"Fix for issue #{issue_number}",
            branch_name,
            "main",
            body=f"Issue #{issue_number} fix via Coder Agent"
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
            ci_status_text = "⚠️ CI тестов не было для этого PR. Либо их не существует"
            client.add_pr_comment(repo_full_name, pr_number, ci_status_text)
            context = f"PR: {pr_title}\nОписание: {pr_body}\nDiff:\n{diff_text}\nCI: {ci_status_text}"
            logger.info(context)
            review_comment = await run_reviewer_agent(context)
            client.add_pr_comment(repo_full_name, pr_number, review_comment)
        else:
            context = f"PR: {pr_title}\nОписание: {pr_body}\nDiff:\n{diff_text}\nCI: {ci_status}"
            review_comment = await run_reviewer_agent(context)
            client.add_pr_comment(repo_full_name, pr_number, review_comment)

        return {"status": "reviewer agent completed"}

    logger.info("Unhandled event type: %s", x_github_event)
    return {"status": "ok"}