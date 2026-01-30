import hashlib
import hmac
import logging
from collections import defaultdict
from typing import List

from fastapi import APIRouter, Request, Header, HTTPException

from main.agents.coder_agent import run_coder_agent
from main.agents.reviewer_agent import run_reviewer_agent
from main.config import WEBHOOK_SECRET
from main.git.github_client import GitHubAppClient

logger = logging.getLogger(__name__)
router = APIRouter()

# ----------------- STATE -----------------
PR_ITERATIONS = defaultdict(int)
MAX_ITERATIONS = 5

# ----------------- UTILS -----------------
def verify_signature(payload: bytes, signature: str) -> bool:
    """Проверка подписи GitHub webhook"""
    mac = hmac.new(WEBHOOK_SECRET.encode(), msg=payload, digestmod=hashlib.sha256)
    return hmac.compare_digest(f"sha256={mac.hexdigest()}", signature)


def is_reviewer_comment(comment_body: str) -> bool:
    """Определяет, что комментарий оставил reviewer agent"""
    return "Вердикт:" in comment_body or comment_body.startswith("[REVIEWER]")


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
    """Получение текущего состояния CI для PR"""
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

# ----------------- WEBHOOK -----------------
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

    # ----------------- Coder Agent: открытие issue -----------------
    if x_github_event == "issues" and payload.get("action") == "opened":
        issue_number = payload["issue"]["number"]
        issue_title = payload["issue"]["title"]
        issue_body = payload["issue"].get("body", "")
        comments = await get_issue_comments(client, repo_full_name, issue_number)

        repo_files = client.list_files(repo_full_name)
        allowed_files = []
        files_context = []

        for path in repo_files:
            content = client.get_file_content(repo_full_name, path, ref="main")
            if content is not None:
                allowed_files.append(path)
                files_context.append(f"=== {path} ===\n{content}")

        context = (
            f"Issue: {issue_title}\n"
            f"Описание: {issue_body}\n"
            f"Комментарии:\n" + "\n".join(comments) + "\n\n" +
            "Содержимое файлов репозитория:\n" + "\n\n".join(files_context)
        )

        files_to_update = await run_coder_agent(context, allowed_files=repo_files)

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

        pr = client.create_pull_request(
            repo_full_name,
            f"Fix for issue #{issue_number}",
            branch_name,
            "main",
            body=f"Issue #{issue_number} fix via Coder Agent"
        )

        # Инициализируем итерацию
        PR_ITERATIONS[pr.number] = 1

        return {"status": "coder agent completed"}

    # ----------------- Reviewer Agent: CI завершился -----------------
    elif x_github_event == "check_run" and payload.get("action") == "completed":
        prs = payload["check_run"].get("pull_requests", [])
        if not prs:
            return {"status": "check_run without PR"}

        pr_number = prs[0]["number"]
        pr = client.get_pull_request(repo_full_name, pr_number)
        pr_title = pr.title
        pr_body = pr.body or ""
        diff_text = await get_pr_diff(client, repo_full_name, pr_number)
        conclusion = payload["check_run"]["conclusion"]

        context = (
            f"PR: {pr_title}\n"
            f"Описание: {pr_body}\n"
            f"Diff:\n{diff_text}\n"
            f"CI статус: {conclusion}"
        )

        review_comment = await run_reviewer_agent(context)
        client.add_pr_comment(repo_full_name, pr_number, review_comment)

        return {"status": "reviewer agent completed"}

    # ----------------- Coder Agent: реагирование на комментарий ревьювера -----------------
    elif x_github_event == "issue_comment" and payload.get("action") == "created":
        comment = payload["comment"]["body"]

        if not is_reviewer_comment(comment):
            return {"status": "not reviewer comment"}

        pr_url = payload["issue"]["pull_request"]["url"]
        pr_number = client.get_pr_number_from_url(pr_url)  # метод для получения PR номера

        # Проверка лимита итераций
        PR_ITERATIONS[pr_number] += 1
        if PR_ITERATIONS[pr_number] > MAX_ITERATIONS:
            client.add_pr_comment(
                repo_full_name,
                pr_number,
                "[SYSTEM] Max iterations reached. Manual intervention required."
            )
            return {"status": "max iterations reached"}

        # Разбираем вердикт reviewer
        verdict = "request changes" if "request changes" in comment.lower() else "approve"
        if verdict == "approve":
            return {"status": "review approved"}

        # Подготовка контекста для coder
        pr = client.get_pull_request(repo_full_name, pr_number)
        pr_title = pr.title
        pr_body = pr.body or ""
        diff_text = await get_pr_diff(client, repo_full_name, pr_number)

        context = (
            f"PR: {pr_title}\n"
            f"Описание: {pr_body}\n"
            f"Текущий diff:\n{diff_text}\n\n"
            f"Комментарий ревьювера:\n{comment}\n\n"
            f"Итерация: {PR_ITERATIONS[pr_number]} из {MAX_ITERATIONS}"
        )

        pr_files = pr.get_files()
        allowed_files = [f.filename for f in pr_files]

        files_to_update = await run_coder_agent(context, allowed_files=allowed_files)
        branch_name = pr.head.ref

        for path, content in files_to_update.items():
            client.create_or_update_file(
                repo_full_name,
                branch_name,
                path,
                content,
                f"Fix after review iteration {PR_ITERATIONS[pr_number]}"
            )

        return {"status": "coder iteration completed"}

    logger.info("Unhandled event type: %s", x_github_event)
    return {"status": "ok"}
