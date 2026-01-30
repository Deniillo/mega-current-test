from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.tools.file import FileTools
from agno.tools.shell import ShellTools
from main.config import OPENROUTER_API_KEY, MODEL

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

def get_coder_agent() -> Agent:
    global _agent
    if _agent is None:
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
