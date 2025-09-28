from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agenticle import Agent, Group, Tool, Endpoint, Model, modelize

# --- Define Tools ---
def get_weather(location: str):
    """Gets weather."""
    return "Sunny"

def get_flights(destination: str):
    """Gets flights."""
    return "Flight ABC"

def main():
    """
    Tests the Model class by first generating a complex YAML config with modelize,
    then loading it with the Model class and verifying the reconstructed structure.
    """
    load_dotenv()
    console = Console()

    # --- Configuration ---
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    model_id = os.getenv("MODEL_ID")
    test_yaml_path = "test_config.yaml"

    if not all([api_key, base_url, model_id]):
        console.print("[bold red]Error: API_KEY, BASE_URL, and MODEL_ID must be set in the .env file.[/bold red]")
        return

    endpoint = Endpoint(name="default_endpoint", api_key=api_key, base_url=base_url)
    
    # --- 1. Define Original In-Memory Structure ---
    weather_agent = Agent(name="WeatherAgent", description="...", input_parameters=[], tools=[Tool(get_weather)], endpoint=endpoint, model_id=model_id)
    flight_agent = Agent(name="FlightAgent", description="...", input_parameters=[], tools=[Tool(get_flights)], endpoint=endpoint, model_id=model_id)
    
    # A group that will be used as a tool
    flight_tools_group = Group(name="FlightToolsGroup", agents=[flight_agent])

    # An agent that uses the group as a tool
    manager_agent = Agent(name="ManagerAgent", description="...", input_parameters=[], tools=[flight_tools_group.as_tool()], endpoint=endpoint, model_id=model_id)

    # A top-level group
    main_group = Group(name="MainTravelGroup", agents=[weather_agent, manager_agent])

    # --- 2. Generate YAML from this structure ---
    console.print(Rule("[bold cyan]Step 1: Generating complex YAML config[/bold cyan]", style="cyan"))
    modelize(groups=[main_group], path=test_yaml_path)
    console.print(f"Generated '{test_yaml_path}' successfully.")

    # --- 3. Load the YAML using the Model class ---
    console.print(Rule("[bold cyan]Step 2: Loading config with Model class[/bold cyan]", style="cyan"))
    
    # Provide the original function tools to the Model loader
    function_tools = [Tool(get_weather), Tool(get_flights)]
    
    try:
        model = Model(path=test_yaml_path, tools=function_tools, endpoints=[endpoint])
        console.print("[bold green]Model loaded successfully![/bold green]")

        # --- 4. Verify the loaded structure ---
        console.print(Rule("[bold cyan]Step 3: Verifying loaded structure[/bold cyan]", style="cyan"))

        # Check agents
        assert "WeatherAgent" in model.agents
        assert "FlightAgent" in model.agents
        assert "ManagerAgent" in model.agents
        console.print("- All agents loaded correctly.")

        # Check groups
        assert "MainTravelGroup" in model.groups
        assert "FlightToolsGroup" in model.groups
        console.print("- All groups loaded correctly.")

        # Check nesting
        loaded_main_group = model.groups["MainTravelGroup"]
        member_names = {member.name for member in loaded_main_group.agent_sequence}
        assert "WeatherAgent" in member_names
        assert "ManagerAgent" in member_names
        console.print("- MainTravelGroup members are correct.")

        # Check tool dependency (Agent using a Group as a tool)
        loaded_manager = model.agents["ManagerAgent"]
        tool_names = {tool.name for tool in loaded_manager.original_tools}
        assert "FlightToolsGroup" in tool_names
        console.print("- ManagerAgent's tool dependency on FlightToolsGroup is correct.")

        console.print("\n[bold green]All assertions passed! The structure was loaded correctly.[/bold green]")

    except Exception as e:
        console.print(f"[bold red]An error occurred: {e}[/bold red]")
    finally:
        # --- 5. Clean up ---
        if os.path.exists(test_yaml_path):
            os.remove(test_yaml_path)
            console.print(f"\nCleaned up {test_yaml_path}.")

if __name__ == "__main__":
    main()
