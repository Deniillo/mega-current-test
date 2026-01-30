from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.tools.file import FileTools
from agno.tools.shell import ShellTools
from main.config import OPENROUTER_API_KEY, MODEL

SYSTEM_PROMPT = """Ты — Reviewer Agent. Твоя задача: проверять pull requests.

Правила:
1. Берем PR title, описание, diff.
2. Проверяем CI результаты.
3. Выдаем вердикт approve или request changes.
4. Комментируем PR с объяснением.

Отвечаем на русском языке.
"""

_agent: Agent | None = None

def get_reviewer_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=OpenRouter(id=MODEL, api_key=OPENROUTER_API_KEY),
            tools=[FileTools(), ShellTools()],
            instructions=SYSTEM_PROMPT,
            markdown=True,
        )
    return _agent

async def run_reviewer_agent(pr_title: str, pr_body: str, diff: str, ci_status: str | None = None) -> str:
    agent = get_reviewer_agent()
    context = f"PR: {pr_title}\nОписание: {pr_body}\nDiff:\n{diff}\nCI: {ci_status}"
    response = agent.run(context)
    return response.content
