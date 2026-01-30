from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from main.config import (
    OPENROUTER_API_KEY, MODEL,
    USE_YANDEX_GPT, YANDEX_CLOUD_API_KEY, YANDEX_CLOUD_FOLDER, YANDEX_CLOUD_MODEL
)
import openai

SYSTEM_PROMPT = """Ты — Coder Agent. Твоя задача: решать задачи из GitHub issues.

Правила:
1. Берем issue title, описание и комментарии.
2. Вносим изменения в проект.
3. Используем git: создаем новую ветку, вносим изменения и пушим.
4. Создаем pull request с описанием изменений.
5. Объясняем, что сделано.

Отвечаем на русском языке.
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
                markdown=True
            )
        else:
            _agent = Agent(
                model=OpenRouter(id=MODEL, api_key=OPENROUTER_API_KEY),
                instructions=SYSTEM_PROMPT,
                markdown=True,
            )
    return _agent

async def run_coder_agent(issue_title: str, issue_body: str, comments: list[str]) -> str:
    agent = get_coder_agent()
    context = f"Issue: {issue_title}\nОписание: {issue_body}\nКомментарии:\n" + "\n".join(comments)
    response = agent.run(context)
    return response.content
