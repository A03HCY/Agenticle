from agenticle.optimizer import NaturalLanguageOptimizer
from agenticle.tool import Tool
from agenticle import Model

# 1. Define some example tool functions
def search_web(query: str) -> str:
    """Searches the web for a given query."""
    return f"Search results for: {query}"

def save_to_file(content: str, filename: str) -> str:
    """Saves content to a file."""
    return f"Content saved to {filename}"

# 2. Create Tool objects from the functions
available_tools = [
    Tool(search_web),
    Tool(save_to_file)
]

# 3. Initialize the optimizer
opt = NaturalLanguageOptimizer()

# 4. Define a requirement that implies the use of the provided tools
requirement = "一个能够研究课题并把结果保存到文件的研究小组"

# 5. Call optimize, passing the available tools
print("--- Testing Group Generation with Tools ---")
res = opt.optimize(
    requirement=requirement,
    group=True,
    tools=available_tools
)
print(res)

Model(res, tools=available_tools)