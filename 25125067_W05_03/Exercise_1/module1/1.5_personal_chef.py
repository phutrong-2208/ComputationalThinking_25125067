from pathlib import Path
import sys

_gemini_root = next(p for p in Path(__file__).resolve().parents
                    if (p / "gemini_setup.py").is_file())
if str(_gemini_root) not in sys.path:
    sys.path.insert(0, str(_gemini_root))
from gemini_setup import load_environment

load_environment(require_api_key=True)

from langchain.tools import tool
from typing import Dict, Any
from langchain_tavily import TavilySearch

tavily_client = TavilySearch(max_results=5)

@tool
def web_search(query: str) -> Dict[str, Any]:

    """Search the web for information"""

    return tavily_client.invoke({"query": query})

system_prompt = """

You are a personal chef. The user will give you a list of ingredients they have left over in their house.

Using the web search tool, search the web for recipes that can be made with the ingredients they have.

Return recipe suggestions and eventually the recipe instructions to the user, if requested.

"""

from langchain.agents import create_agent

agent = create_agent(
    model="google_genai:gemini-3.7-flash",
    tools=[web_search],
    system_prompt=system_prompt
)