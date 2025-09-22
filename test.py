import os
from dotenv import load_dotenv
from agenticle import Agent, Group, Tool, Endpoint, Event
# Import rich components
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.style import Style

# --- Define a Theme for Consistency ---
STYLES = {
    "group": Style(color="magenta", bold=True),
    "manager": Style(color="cyan", bold=True),
    "agent": Style(color="green", bold=True),
    "reasoning": Style(color="grey50", italic=True),
    "decision": Style(color="blue", bold=True),
    "tool_result": Style(color="yellow"),
    "error": Style(color="red", bold=True),
    "final_answer": Style(color="default", bold=True),
}
def print_event(event: Event, console: Console):
    """
    Renders an agent event to the console using the rich library for beautiful output.
    Args:
        event (Event): The event object to print.
        console (Console): The rich Console instance to use for printing.
    """
    source_name = event.source.split(':')[-1]
    
    # Determine the base style for the source
    if "Group" in event.source:
        base_style = STYLES["group"]
    elif "Manager" in event.source or "Planner" in event.source:
        base_style = STYLES["manager"]
    else:
        base_style = STYLES["agent"]
    # --- Handle each event type with a specific rich component ---
    if event.type == "start":
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold")
        table.add_column()
        for key, value in event.payload.items():
            table.add_row(f"{key}:", str(value))
        
        console.print(
            Panel(
                table,
                title=f"🚀 [bold]{source_name} Started[/]",
                border_style=base_style,
                expand=False
            )
        )
    elif event.type == "step":
        console.print(Rule(f"{event.source} Step {event.payload['current_step']}", style=base_style))
    elif event.type == "reasoning_stream":
        console.print(Text(event.payload["content"], style=STYLES["reasoning"]), end="")
    elif event.type == "content_stream":
        console.print(Text(event.payload["content"], style="default"), end="")
    elif event.type == "decision":
        tool_name = event.payload['tool_name']
        tool_args = event.payload['tool_args']
        # The newline ensures it appears after any streamed "thinking" text
        console.print(f"\n✅ [bold]Action:[/] Calling tool `[{base_style}]{tool_name}[/{base_style}]` with args: {tool_args}")
    elif event.type == "tool_result":
        output_text = Text(str(event.payload.get("output", "No output")), style=STYLES["tool_result"])
        tool_name = event.payload['tool_name']
        
        panel_title = f"Result from `[bold]{tool_name}[/]`"
        console.print(
            Panel(output_text, title=panel_title, border_style=STYLES["tool_result"], expand=False)
        )
    elif event.type == "end":
        final_answer = event.payload.get("final_answer") or event.payload.get("result", "No result found.")
        title = "🏁 Mission Complete" if "Agent" in event.source else "🏁 Group Finished"
        
        console.print()
        console.print(
            Panel(
                Text(str(final_answer), justify="center", style=STYLES["final_answer"]),
                title=f"[{base_style}]{title}[/{base_style}]",
                border_style=base_style,
                padding=(1, 2)
            )
        )
    elif event.type == "error":
        console.print(
            Panel(
                Text(event.payload.get("message", "An unknown error occurred."), justify="left"),
                title=f"❌ ERROR in {source_name}",
                border_style=STYLES["error"]
            )
        )
        
    else:
        return
        # Fallback for any other event types
        console.rule(f"Unknown Event: {event.type}", style="red")
        console.print(event.payload)

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

if __name__ == "__main__":
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
        model_id=model_id
    )

    search_agent = Agent(
        name="Attraction_Search_Specialist",
        description="专门用来查找一个城市的旅游景点。",
        input_parameters=[{"name": "location"}],
        tools=[Tool(find_tourist_attractions)],
        endpoint=openai_endpoint,
        model_id=model_id
    )

    # --- 3. 创建管理者 Agent ---
    # 管理者没有任何自己的工具，它的职责是规划和委派。
    planner_agent = Agent(
        name="Planner_Manager",
        description="一个智能规划者，负责理解用户的复杂旅行请求，并将任务分解给合适的专家。它负责协调整个流程并给出最终答复。",
        input_parameters=[{"name": "user_request"}],
        tools=[], # No direct tools, it delegates
        endpoint=openai_endpoint,
        model_id=model_id
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
