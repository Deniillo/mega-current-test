import jwt
import time
import requests
from github import Github

from app.config import GITHUB_APP_ID, GITHUB_PRIVATE_KEY_PATH

class GitHubAppClient:
    def __init__(self, installation_id: int):
        self.installation_id = installation_id
        self.token = self.get_installation_token()
        self.client = Github(self.token)

    def get_jwt(self):
        with open(GITHUB_PRIVATE_KEY_PATH, "r") as f:
            private_key = f.read()
        payload = {
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,  # JWT действует 10 минут
            "iss": GITHUB_APP_ID
        }
        return jwt.encode(payload, private_key, algorithm="RS256")

    def get_installation_token(self):
        jwt_token = self.get_jwt()
        url = f"https://api.github.com/app/installations/{self.installation_id}/access_tokens"
        headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json"}
        resp = requests.post(url, headers=headers)
        resp.raise_for_status()
        return resp.json()["token"]

    def get_repo(self, full_name: str):
        return self.client.get_repo(full_name)

    # -----------------------------
    # Issues
    # -----------------------------
    def get_issue(self, repo_full_name: str, issue_number: int):
        repo = self.get_repo(repo_full_name)
        return repo.get_issue(number=issue_number)

    # -----------------------------
    # Pull Requests
    # -----------------------------
    def get_pull_request(self, repo_full_name: str, pr_number: int):
        repo = self.get_repo(repo_full_name)
        return repo.get_pull(pr_number)

    def create_pull_request(self, repo_full_name: str, title: str, head: str, base: str, body: str = ""):
        repo = self.get_repo(repo_full_name)
        return repo.create_pull(title=title, body=body, head=head, base=base)

    def add_pr_comment(self, repo_full_name: str, pr_number: int, comment: str):
        pr = self.get_pull_request(repo_full_name, pr_number)
        pr.create_issue_comment(comment)

    def get_pr_files(self, repo_full_name: str, pr_number: int):
        pr = self.get_pull_request(repo_full_name, pr_number)
        return pr.get_files()

    def get_pr_diff(self, repo_full_name: str, pr_number: int):
        pr = self.get_pull_request(repo_full_name, pr_number)
        return pr.patch  # raw diff

    # -----------------------------
    # Branches
    # -----------------------------
    def create_branch(self, repo_full_name: str, branch_name: str, source_branch: str = "main"):
        repo = self.get_repo(repo_full_name)
        source = repo.get_branch(source_branch)
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)

    # -----------------------------
    # Files
    # -----------------------------
    def create_or_update_file(self, repo_full_name: str, branch: str, path: str, content: str, message: str):
        repo = self.get_repo(repo_full_name)
        try:
            f = repo.get_contents(path, ref=branch)
            repo.update_file(path, message, content, f.sha, branch=branch)
        except:
            repo.create_file(path, message, content, branch=branch)

    def delete_file(self, repo_full_name: str, branch: str, path: str, message: str):
        repo = self.get_repo(repo_full_name)
        f = repo.get_contents(path, ref=branch)
        repo.delete_file(path, message, f.sha, branch=branch)

    def get_file_content(self, repo_full_name: str, path: str, ref: str = "main"):
        repo = self.get_repo(repo_full_name)
        f = repo.get_contents(path, ref=ref)
        return f.decoded_content.decode()

    def list_files(self, repo_full_name: str, path: str = "", ref: str = "main"):
        repo = self.get_repo(repo_full_name)
        result = []
        contents = repo.get_contents(path, ref=ref)
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(repo.get_contents(file_content.path, ref=ref))
            else:
                result.append(file_content.path)
        return result
