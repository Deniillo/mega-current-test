import openai
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from main.config import (
    OPENROUTER_API_KEY, MODEL,
    USE_YANDEX_GPT, YANDEX_CLOUD_API_KEY, YANDEX_CLOUD_FOLDER, YANDEX_CLOUD_MODEL
)

SYSTEM_PROMPT = """Ты — Coder Agent. Твоя задача — исправлять баги и добавлять функционал по issue.

Правила формата ответа:
1. Каждый изменяемый или создаваемый файл выводи в таком формате:
=== путь/к/файлу ===
<код файла>
2. Никаких пояснений, комментариев или текста вне блоков файлов — только файлы.
3. Сохраняй отступы и синтаксис файлов без изменений.
4. Не объединяй несколько файлов в один блок.
5. Если файл не нужно менять — не упоминай его.
6. Код должен быть корректным для соответствующего языка (Python, JS, etc.).
7. Не добавляй никаких других инструкций, только файлы в указанном формате.

Пример корректного ответа:
=== app/main.py ===
print("Hello world")

=== utils/helpers.py ===
def add(a, b):
    return a + b
"""


class LLMAgent:
    """
    Универсальный агент для OpenRouter и YandexGPT через OpenAI SDK.
    """
    def __init__(self):
        if USE_YANDEX_GPT:
            self.client = openai.OpenAI(
                api_key=YANDEX_CLOUD_API_KEY,
                base_url="https://rest-assistant.api.cloud.yandex.net/v1",
                project=YANDEX_CLOUD_FOLDER
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
                max_output_tokens=500
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
                max_tokens=500
            )
            return resp.choices[0].message.content


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


# Singleton агента
_agent: LLMAgent | None = None

def get_coder_agent() -> LLMAgent:
    global _agent
    if _agent is None:
        _agent = LLMAgent()
    return _agent


async def run_coder_agent(issue_title: str, issue_body: str, comments: list[str]) -> dict[str, str]:
    """
    Возвращает словарь {файл: новый код}.
    """
    agent = get_coder_agent()
    context = f"Issue: {issue_title}\nОписание: {issue_body}\nКомментарии:\n" + "\n".join(comments)
    response = await agent.run(context)
    files_to_update = parse_agent_diff(response)
    return files_to_update
