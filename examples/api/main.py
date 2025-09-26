import os
import sys
from dotenv import load_dotenv

# Add the project root to the Python path to ensure agenticle is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from agenticle import Agent, Group, Tool, Endpoint
import agenticle.server as server

# This example requires the API dependencies.
# Install them with: pip install "agenticle[api]"

# --- Define Tools ---
def get_current_weather(location: str):
    """Gets the current weather for a specified location."""
    return f"Weather in {location}: 15 degrees Celsius, sunny."

def find_tourist_attractions(location: str):
    """Finds popular tourist attractions for a specified location."""
    if location.lower() == "beijing":
        return "Popular attractions in Beijing include: the Great Wall, the Forbidden City, and the Summer Palace."
    return f"Could not find attractions for {location}."

def get_flight_info(destination: str):
    """Gets flight information for a specified destination. This is a shared tool."""
    return f"Flight to {destination} is available on XYZ Airline at 8:00 AM."

def main():
    """
    Main function to set up a multi-agent group and start the API server.
    """
    load_dotenv()

    # --- 1. Load configuration from .env file ---
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    model_id = os.getenv("MODEL_ID")

    if not all([api_key, base_url, model_id]):
        print("Error: API_KEY, BASE_URL, and MODEL_ID must be set in the .env file.")
        print("Please create a .env file in the root directory with the required variables.")
        return

    openai_endpoint = Endpoint(
        api_key=api_key,
        base_url=base_url
    )

    # --- 2. Create Specialist Agents and Tools ---
    weather_agent = Agent(
        name="Weather_Specialist",
        description="Specializes in fetching weather information for a given city.",
        input_parameters=[{"name": "location"}],
        tools=[Tool(get_current_weather)],
        endpoint=openai_endpoint,
        model_id=model_id,
    )

    search_agent = Agent(
        name="Attraction_Search_Specialist",
        description="Specializes in finding tourist attractions in a city.",
        input_parameters=[{"name": "location"}],
        tools=[Tool(find_tourist_attractions)],
        endpoint=openai_endpoint,
        model_id=model_id,
    )

    # --- 3. Create a Manager Agent ---
    planner_agent = Agent(
        name="Planner_Manager",
        description="A smart planner that understands complex user travel requests, breaks them down, and delegates tasks to the appropriate specialist.",
        input_parameters=[{"name": "user_request"}],
        tools=[],  # The manager delegates
        endpoint=openai_endpoint,
        model_id=model_id,
    )

    # --- 4. Assemble the Group ---
    travel_agency = Group(
        name="Travel_Agency",
        agents=[planner_agent, weather_agent, search_agent],
        manager_agent_name="Planner_Manager",
        shared_tools=[Tool(get_flight_info)],
        mode='manager_delegation'
    )

    # --- 5. Register the Group with the Server ---
    # The API will expose the 'Travel_Agency' group under this name.
    server.register("travel_agency", travel_agency)
    server.register("weather_agent", weather_agent) # also register a single agent for demo

    # --- 6. Start the API Server ---
    print("Starting Agenticle API server...")
    print("Try calling the API. For example, using curl:")
    print("""
    # --- To stream events from the Travel_Agency group ---
    curl -X POST http://127.0.0.1:8000/v1/tasks/stream -H "Content-Type: application/json" -d '{"agent_or_group_name": "travel_agency", "input_data": {"user_request": "I want to go to Beijing. Can you help me plan the trip?"}}'
    
    # --- To run the single weather_agent asynchronously ---
    curl -X POST http://127.0.0.1:8000/v1/tasks -H "Content-Type: application/json" -d '{"agent_or_group_name": "weather_agent", "input_data": {"city": "Tokyo"}}'
    """)
    server.run()

if __name__ == "__main__":
    main()
