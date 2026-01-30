from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from main.config import (
    OPENROUTER_API_KEY, MODEL,
    USE_YANDEX_GPT, YANDEX_CLOUD_API_KEY, YANDEX_CLOUD_FOLDER, YANDEX_CLOUD_MODEL
)
import openai

SYSTEM_PROMPT = """Ты — Coder Agent. Твоя задача — исправлять баги и добавлять функционал по issue.

Инструкции:
напиши что-нибудь
"""

_agent: Agent | None = None


class YandexGPT(OpenRouter):
    def __init__(self, folder: str, api_key: str, model_name: str):
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://rest-assistant.api.cloud.yandex.net/v1",
            project=folder
        )
        self.model_id = f"gpt://{folder}/{model_name}"

    def run(self, prompt: str):
        resp = self.client.responses.create(
            model=self.model_id,
            instructions=SYSTEM_PROMPT,
            input=prompt,
            temperature=0.3,
            max_output_tokens=500
        )
        class Resp:
            content = resp.output_text
        return Resp()


def get_coder_agent() -> Agent:
    global _agent
    if _agent is None:
        if USE_YANDEX_GPT:
            _agent = Agent(
                model=YandexGPT(YANDEX_CLOUD_FOLDER, YANDEX_CLOUD_API_KEY, YANDEX_CLOUD_MODEL),
                instructions=SYSTEM_PROMPT,
                markdown=False
            )
        else:
            _agent = Agent(
                model=OpenRouter(id=MODEL, api_key=OPENROUTER_API_KEY),
                instructions=SYSTEM_PROMPT,
                markdown=False
            )
    return _agent


def parse_agent_diff(agent_response: str) -> dict[str, str]:
    """
    Преобразует ответ агента в словарь {путь_файла: новый_код}.
    Формат ответа:
    === filename ===
    <код файла>
    """
    files = {}
    current_file = None
    buffer = []

    for line in agent_response.splitlines():
        line = line.rstrip()
        if line.startswith("===") and line.endswith("==="):
            if current_file:
                files[current_file] = "\n".join(buffer).strip()
            current_file = line.strip("= ").strip()
            buffer = []
        else:
            buffer.append(line)
    if current_file:
        files[current_file] = "\n".join(buffer).strip()
    return files


async def run_coder_agent(issue_title: str, issue_body: str, comments: list[str]) -> dict[str, str]:
    """
    Возвращает словарь {файл: новый код}.
    """
    agent = get_coder_agent()
    context = f"Issue: {issue_title}\nОписание: {issue_body}\nКомментарии:\n" + "\n".join(comments)
    response = agent.run(context)
    files_to_update = parse_agent_diff(response.content)
    return files_to_update
