import openai
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from main.config import OPENROUTER_API_KEY, MODEL, USE_YANDEX_GPT, YANDEX_CLOUD_API_KEY, YANDEX_CLOUD_FOLDER, YANDEX_CLOUD_MODEL

SYSTEM_PROMPT = """
Ты — Reviewer Agent. Твоя задача: проверять pull requests.

Правила:
1. Берем PR title, описание, diff.
2. Проверяем CI результаты.
3. Выдаем вердикт approve или request changes.
4. Комментируем PR с объяснением.
5. Отвечаем на русском языке.

Если не понял задачу — напиши "Я не понял задачу".
"""

class LLMAgent:
    """Универсальный агент для OpenRouter и YandexGPT через OpenAI SDK."""
    def __init__(self):
        if USE_YANDEX_GPT:
            self.client = openai.OpenAI(
                api_key=YANDEX_CLOUD_API_KEY,
                base_url="https://rest-assistant.api.cloud.yandex.net/v1",
                project=YANDEX_CLOUD_FOLDER,
            )
            self.model_id = f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}"
            self.is_yandex = True
        else:
            self.client = openai.OpenAI(api_key=OPENROUTER_API_KEY)
            self.model_id = MODEL
            self.is_yandex = False

    async def run(self, prompt: str) -> str:
        if self.is_yandex:
            resp = self.client.responses.create(
                model=self.model_id,
                instructions=SYSTEM_PROMPT,
                input=prompt,
                temperature=0.3,
                max_output_tokens=5000
            )
            return resp.output_text
        else:
            resp = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    ChatCompletionSystemMessageParam(content=SYSTEM_PROMPT, role="system"),
                    ChatCompletionUserMessageParam(content=prompt, role="user")
                ],
                temperature=0.3,
                max_tokens=1000
            )
            return resp.choices[0].message.content

# Singleton агента
_agent: LLMAgent | None = None

def get_reviewer_agent() -> LLMAgent:
    global _agent
    if _agent is None:
        _agent = LLMAgent()
    return _agent

async def run_reviewer_agent(context: str) -> str:
    """
    Запускает агента на произвольном контексте PR и возвращает вердикт и комментарий.
    Контекст должен быть полностью собран до вызова функции.
    """
    agent = get_reviewer_agent()
    response = await agent.run(context)
    return response.strip()
