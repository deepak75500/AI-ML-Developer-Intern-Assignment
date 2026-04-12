
import os
from dotenv import load_dotenv
import sqlite3

load_dotenv()

from vanna import Agent
from vanna.core.registry import ToolRegistry
from vanna.core.user import UserResolver, User, RequestContext
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
    SaveTextMemoryTool
)
from vanna.integrations.sqlite import SqliteRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory

# 🔥 GROQ IMPORT
from groq import Groq

DB_PATH = os.getenv("DB_PATH", "clinic.db")


# ── Extract DB Schema ─────────────────────────────────────────────────────────
def get_schema():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    schema_text = ""

    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table';"
    ).fetchall()

    for (table,) in tables:
        columns = cur.execute(f"PRAGMA table_info({table});").fetchall()
        schema_text += f"\nTable: {table}\n"
        for col in columns:
            schema_text += f"  - {col[1]} ({col[2]})\n"

    conn.close()
    return schema_text


SCHEMA = get_schema()


# ── Custom Groq LLM Wrapper ───────────────────────────────────────────────────
class GroqLlmService:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    async def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="openai/gpt-oss-120b",  # 🔥 Best for SQL
            messages=[
                {
                    "role": "system",
                    "content": f"""
You are an expert SQL generator.

STRICT RULES:
- Only generate SQLite SELECT queries
- No explanations
- No markdown
- No comments
- Use ONLY tables/columns from schema

DATABASE SCHEMA:
{SCHEMA}
"""
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        return response.choices[0].message.content.strip()


# ── User Resolver ─────────────────────────────────────────────────────────────
class DefaultUserResolver(UserResolver):
    async def resolve_user(self, context: RequestContext) -> User:
        return User(
            id="default",
            email="default@clinic.com",
            group_memberships=["admin"]
        )


# ── Create Agent ──────────────────────────────────────────────────────────────
def create_agent():
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set")

    llm = GroqLlmService(api_key)

    db_tool = RunSqlTool(
        sql_runner=SqliteRunner(database_path=DB_PATH)
    )

    memory = DemoAgentMemory(max_items=1000)

    registry = ToolRegistry()
    registry.register_local_tool(db_tool, access_groups=["admin"])
    registry.register_local_tool(SaveQuestionToolArgsTool(), access_groups=["admin"])
    registry.register_local_tool(SearchSavedCorrectToolUsesTool(), access_groups=["admin"])
    registry.register_local_tool(SaveTextMemoryTool(), access_groups=["admin", "user"])
    registry.register_local_tool(VisualizeDataTool(), access_groups=["admin"])

    agent = Agent(
        llm_service=llm,
        tool_registry=registry,
        user_resolver=DefaultUserResolver(),
        agent_memory=memory,
    )

    return agent, memory


agent, agent_memory = create_agent()