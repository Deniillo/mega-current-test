import jwt
import time
import requests
import logging

logger = logging.getLogger("github_app.client")
from github import Github

from main.config import GITHUB_APP_ID, GITHUB_PRIVATE_KEY_PATH

class GitHubAppClient:
    def __init__(self, installation_id: int):
        self.installation_id = installation_id
        logger.info(
            "GitHubAppClient init installation_id=%s",
            installation_id,
        )

        self.token = self.get_installation_token()
        self.client = Github(self.token)

    def get_jwt(self):
        logger.debug(
            "Generating JWT (app_id=%s)",
            GITHUB_APP_ID,
        )

        try:
            with open(GITHUB_PRIVATE_KEY_PATH, "r") as f:
                private_key = f.read()
        except Exception:
            logger.exception("Failed to read private key")
            raise

        payload = {
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "iss": GITHUB_APP_ID,
        }

        token = jwt.encode(payload, private_key, algorithm="RS256")
        logger.debug("JWT generated successfully")

        return token

    def get_installation_token(self):
        logger.info(
            "Requesting installation token installation_id=%s",
            self.installation_id,
        )

        jwt_token = self.get_jwt()
        url = (
            f"https://api.github.com/app/installations/"
            f"{self.installation_id}/access_tokens"
        )

        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        }

        try:
            resp = requests.post(url, headers=headers, timeout=10)
            logger.debug(
                "GitHub token response status=%s body=%s",
                resp.status_code,
                resp.text,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to obtain installation token")
            raise

        token = resp.json()["token"]
        logger.info("Installation token obtained successfully")

        return token

    def get_repo(self, full_name: str):
        logger.debug("Fetching repo full_name=%s", full_name)
        try:
            repo = self.client.get_repo(full_name)
            logger.debug("Repo fetched successfully full_name=%s", full_name)
            return repo
        except Exception:
            logger.exception("Failed to fetch repo full_name=%s", full_name)
            raise

    def get_issue(self, repo_full_name: str, issue_number: int):
        logger.info(
            "Fetching issue repo=%s issue_number=%s",
            repo_full_name,
            issue_number,
        )
        try:
            repo = self.get_repo(repo_full_name)
            issue = repo.get_issue(number=issue_number)
            logger.debug("Issue fetched successfully")
            return issue
        except Exception:
            logger.exception(
                "Failed to fetch issue repo=%s issue_number=%s",
                repo_full_name,
                issue_number,
            )
            raise

    def get_pull_request(self, repo_full_name: str, pr_number: int):
        logger.info(
            "Fetching PR repo=%s pr_number=%s",
            repo_full_name,
            pr_number,
        )
        try:
            repo = self.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            logger.debug("PR fetched successfully")
            return pr
        except Exception:
            logger.exception(
                "Failed to fetch PR repo=%s pr_number=%s",
                repo_full_name,
                pr_number,
            )
            raise

    def create_pull_request(
        self,
        repo_full_name: str,
        title: str,
        head: str,
        base: str,
        body: str = "",
    ):
        logger.info(
            "Creating PR repo=%s head=%s base=%s title=%s",
            repo_full_name,
            head,
            base,
            title,
        )

        try:
            repo = self.get_repo(repo_full_name)
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head,
                base=base,
            )
            logger.info("PR created successfully pr_number=%s", pr.number)
            return pr
        except Exception:
            logger.exception("Failed to create PR repo=%s", repo_full_name)
            raise

    def add_pr_comment(self, repo_full_name: str, pr_number: int, comment: str):
        logger.info(
            "Adding PR comment repo=%s pr_number=%s",
            repo_full_name,
            pr_number,
        )

        try:
            pr = self.get_pull_request(repo_full_name, pr_number)
            pr.create_issue_comment(comment)
            logger.info("PR comment added successfully")
        except Exception:
            logger.exception(
                "Failed to add PR comment repo=%s pr_number=%s",
                repo_full_name,
                pr_number,
            )
            raise

    def create_or_update_file(
        self,
        repo_full_name: str,
        branch: str,
        path: str,
        content: str,
        message: str,
    ):
        logger.info(
            "Create/update file repo=%s branch=%s path=%s",
            repo_full_name,
            branch,
            path,
        )

        repo = self.get_repo(repo_full_name)

        try:
            f = repo.get_contents(path, ref=branch)
            logger.debug("File exists, updating path=%s", path)

            repo.update_file(
                path,
                message,
                content,
                f.sha,
                branch=branch,
            )
            logger.info("File updated successfully path=%s", path)
        except Exception:
            logger.debug("File not found, creating path=%s", path)
            try:
                repo.create_file(
                    path,
                    message,
                    content,
                    branch=branch,
                )
                logger.info("File created successfully path=%s", path)
            except Exception:
                logger.exception(
                    "Failed to create/update file repo=%s path=%s",
                    repo_full_name,
                    path,
                )
                raise

    def delete_file(self, repo_full_name: str, branch: str, path: str, message: str):
        logger.info(
            "Deleting file repo=%s branch=%s path=%s",
            repo_full_name,
            branch,
            path,
        )
        try:
            repo = self.get_repo(repo_full_name)
            f = repo.get_contents(path, ref=branch)
            repo.delete_file(path, message, f.sha, branch=branch)
            logger.info("File deleted successfully path=%s", path)
        except Exception:
            logger.exception("Failed to delete file path=%s", path)
            raise

    def get_file_content(self, repo_full_name: str, path: str, ref: str = "main"):
        """
        Возвращает содержимое текстового файла. Если файл бинарный, возвращает None
        """
        logger.debug("Reading file repo=%s ref=%s path=%s", repo_full_name, ref, path)
        try:
            repo = self.get_repo(repo_full_name)
            f = repo.get_contents(path, ref=ref)

            try:
                return f.decoded_content.decode("utf-8")
            except UnicodeDecodeError:
                logger.info("Skipping binary file %s", path)
                return None
        except Exception:
            logger.exception("Failed to read file path=%s", path)
            return None

    def list_files(self, repo_full_name: str, path: str = "", ref: str = "main"):
        logger.info("Listing files repo=%s ref=%s path=%s", repo_full_name, ref, path)
        try:
            repo = self.get_repo(repo_full_name)
            result = []
            contents = repo.get_contents(path, ref=ref)

            while contents:
                item = contents.pop(0)
                if item.type == "dir":
                    contents.extend(repo.get_contents(item.path, ref=ref))
                else:
                    result.append(item.path)

            logger.info("Files listed count=%s", len(result))
            return result
        except Exception:
            logger.exception("Failed to list files repo=%s", repo_full_name)
            return []

    def create_branch(self, repo_full_name: str, branch_name: str, base_branch: str = "main"):
        """
        Создает новую ветку branch_name от base_branch
        """
        logger.info(
            "Creating branch repo=%s branch_name=%s base_branch=%s",
            repo_full_name,
            branch_name,
            base_branch,
        )

        try:
            repo = self.get_repo(repo_full_name)

            base_ref = repo.get_branch(base_branch)

            repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_ref.commit.sha)
            logger.info(
                "Branch created successfully branch_name=%s from base_branch=%s",
                branch_name,
                base_branch,
            )
        except Exception:
            logger.exception(
                "Failed to create branch repo=%s branch_name=%s",
                repo_full_name,
                branch_name,
            )
            raise

    def get_pr_number_from_url(self, pr_url: str) -> int:
        """
        Получает номер PR из полного API URL
        """
        try:
            pr_number = int(pr_url.rstrip("/").split("/")[-1])
            return pr_number
        except Exception:
            logger.exception("Failed to parse PR number from URL: %s", pr_url)
            raise
