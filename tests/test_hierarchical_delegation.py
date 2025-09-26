import os
from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.utils import print_event
from agenticle import Agent, Group, Tool, Endpoint

# --- Define a simple tool for the sub-group agent ---
def perform_research(topic: str) -> str:
    """Performs basic research on a given topic."""
    print(f"--- (Inner Tool) Performing research on: {topic} ---")
    if "AI" in topic:
        return "AI is rapidly evolving, with major advancements in large language models and generative art."
    return "Research topic not recognized."

def main():
    load_dotenv()
    
    # --- Load configuration from .env file ---
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    model_id = os.getenv("MODEL_ID")

    if not api_key or not base_url or not model_id:
        raise ValueError("API_KEY, BASE_URL, and MODEL_ID must be set in the .env file.")

    openai_endpoint = Endpoint(
        api_key=api_key,
        base_url=base_url
    )
    console = Console()

    # --- 1. Define the Sub-Group (Research Team) ---
    researcher_agent = Agent(
        name="Researcher",
        description="An expert agent that uses its tools to conduct research on a given topic and returns the findings.",
        input_parameters=[{"name": "topic", "description": "The subject to research."}],
        tools=[Tool(perform_research)],
        endpoint=openai_endpoint,
        model_id=model_id,
        optimize_tool_call=True
    )

    research_team = Group(
        name="research_team",
        description="A specialized team for conducting in-depth research. When you delegate a task to this team, they will handle the entire research process and provide a complete summary.",
        agents=[researcher_agent],
        mode='manager_delegation' # The group itself has a manager
    )

    # --- 2. Convert the Sub-Group into a Tool ---
    research_team_tool = research_team.as_tool()
    console.print(Rule("[bold yellow]Created a sub-group and converted it into a tool[/]", style="yellow"))
    console.print(f"Tool Name: {research_team_tool.name}")
    console.print(f"Tool Description: {research_team_tool.description}")
    console.print(f"Tool Parameters: {research_team_tool.parameters}")


    # --- 3. Define the Top-Level Group (Project Management Team) ---
    project_manager_agent = Agent(
        name="Project_Manager",
        description="You are a project manager. Your job is to understand complex user requests and delegate them to the appropriate expert teams or agents. You have a 'research_team' available to you. CRITICAL: After receiving the result from a delegated team, you must formulate a final, user-facing answer based on their findings and then use the 'end_task' tool to conclude the mission.",
        input_parameters=[{"name": "user_request", "description": "The user's high-level request."}],
        tools=[research_team_tool], # The manager's tool is the entire sub-group
        endpoint=openai_endpoint,
        model_id=model_id,
        optimize_tool_call=True
    )

    project_management_team = Group(
        name="Project_Management_Team",
        agents=[project_manager_agent],
        manager_agent_name="Project_Manager",
        mode='manager_delegation'
    )
    console.print(Rule("[bold cyan]Created the top-level management team[/]", style="cyan"))

    # --- 4. Run a Task that Requires Hierarchical Delegation ---
    user_query = "I need a summary of the latest advancements in AI."
    console.print(Rule(f"[bold]Executing Hierarchical Task: '{user_query}'[/]", style="magenta"))

    event_stream = project_management_team.run(stream=True, user_request=user_query)

    for event in event_stream:
        print_event(event, console)
        
    console.print(Rule("[bold green]Hierarchical Delegation Test Finished[/]", style="green"))

if __name__ == "__main__":
    main()
