import os
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.syntax import Syntax

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agenticle import Agent, Group, Tool, Endpoint, modeliz

# --- Define Tools ---
def get_weather(location: str):
    """Gets weather."""
    return "Sunny"

def get_flights(destination: str):
    """Gets flights."""
    return "Flight ABC"

def main():
    """
    Tests the modeliz function by creating a nested group structure,
    serializing it to YAML, and printing the result.
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

    endpoint = Endpoint(api_key=api_key, base_url=base_url)

    # --- 1. Define Agents and Nested Groups ---
    console.print("[bold cyan]--- Defining Nested Agent Structure ---[/bold cyan]")
    
    weather_agent = Agent(
        name="WeatherAgent",
        description="An agent for weather.",
        input_parameters=[],
        tools=[Tool(get_weather)],
        endpoint=endpoint,
        model_id=model_id
    )

    flight_agent = Agent(
        name="FlightAgent",
        description="An agent for flights.",
        input_parameters=[],
        tools=[Tool(get_flights)],
        endpoint=endpoint,
        model_id=model_id
    )

    sub_group = Group(
        name="SubTravelGroup",
        agents=[flight_agent],
        description="A subgroup for flight-related tasks."
    )

    main_group = Group(
        name="MainTravelGroup",
        agents=[weather_agent, sub_group],
        description="A main group that delegates to agents and subgroups."
    )
    
    console.print("Structure defined:")
    console.print("- MainTravelGroup")
    console.print("  - WeatherAgent")
    console.print("  - SubTravelGroup")
    console.print("    - FlightAgent")

    # --- 2. Serialize using modeliz ---
    console.print(f"\n[bold cyan]--- Serializing structure to {test_yaml_path} ---[/bold cyan]")
    
    # We only need to pass the top-level group. 
    # modeliz should discover all nested agents and groups.
    modeliz(groups=[main_group], path=test_yaml_path)

    # --- 3. Read and Print the YAML Output ---
    if os.path.exists(test_yaml_path):
        console.print(f"[bold green]Successfully created YAML file.[/bold green]")
        with open(test_yaml_path, 'r', encoding='utf-8') as f:
            content = f.read()
            syntax = Syntax(content, "yaml", theme="default", line_numbers=True)
            console.print("\n[bold]Generated YAML content:[/bold]")
            console.print(syntax)
        
        # Clean up the test file
        os.remove(test_yaml_path)
        console.print(f"\n[bold]Cleaned up {test_yaml_path}.[/bold]")
    else:
        console.print("[bold red]Error: YAML file was not created.[/bold red]")

if __name__ == "__main__":
    main()
