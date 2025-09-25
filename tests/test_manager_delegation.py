import os
from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.utils import print_event
from agenticle   import Agent, Group, Tool, Endpoint

# --- Define Tools ---
def get_current_weather(location: str):
    """获取指定地点的当前天气信息。"""
    return f"Weather in {location}: 15 degrees Celsius, sunny."

def find_tourist_attractions(location: str):
    """查找指定地点的热门旅游景点。"""
    if location.lower() == "beijing":
        return "Popular attractions in Beijing include: the Great Wall, the Forbidden City, and the Summer Palace."
    return f"Could not find attractions for {location}."

def get_flight_info(destination: str):
    """获取飞往指定目的地的航班信息。这是一个团队共享工具。"""
    return f"Flight to {destination} is available on XYZ Airline at 8:00 AM."

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

    # --- 1. 定义团队共享工具 ---
    shared_flight_tool = Tool(get_flight_info)

    # --- 2. 创建专家 Agents ---
    weather_agent = Agent(
        name="Weather_Specialist",
        description="专门用来查询特定城市的天气信息。",
        input_parameters=[{"name": "location"}],
        tools=[Tool(get_current_weather)],
        endpoint=openai_endpoint,
        model_id=model_id,
        optimize_tool_call=True
    )

    search_agent = Agent(
        name="Attraction_Search_Specialist",
        description="专门用来查找一个城市的旅游景点。",
        input_parameters=[{"name": "location"}],
        tools=[Tool(find_tourist_attractions)],
        endpoint=openai_endpoint,
        model_id=model_id,
        optimize_tool_call=True
    )

    # --- 3. 创建管理者 Agent ---
    # 管理者没有任何自己的工具，它的职责是规划和委派。
    planner_agent = Agent(
        name="Planner_Manager",
        description="一个智能规划者，负责理解用户的复杂旅行请求，并将任务分解给合适的专家。它负责协调整个流程并给出最终答复。",
        input_parameters=[{"name": "user_request"}],
        tools=[], # No direct tools, it delegates
        endpoint=openai_endpoint,
        model_id=model_id,
        optimize_tool_call=True
    )

    # --- 4. 组建团队 (Group) ---
    travel_agency = Group(
        name="Travel_Agency",
        agents=[planner_agent, weather_agent, search_agent],
        manager_agent_name="Planner_Manager",
        shared_tools=[shared_flight_tool],
        mode='manager_delegation' # 使用委派模式
    )

    # --- 5. 运行一个需要协作的复杂任务 ---
    user_query = "我想去北京旅行，现在天气怎么样？有哪些著名的景点？另外帮我看看航班信息。"

    console.print(Rule(f"[bold]Executing Complex Task for Group: {travel_agency.name}[/]", style="magenta"))
    
    event_stream = travel_agency.run(stream=True, user_request=user_query)

    for event in event_stream:
        print_event(event, console)
        
    print("\n\n--- Group task finished ---")

if __name__ == "__main__":
    main()
