import time
from dotenv import load_dotenv

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.utils import print_event
from agenticle   import Agent, Group, Tool, Endpoint
from rich.console import Console
from rich.rule import Rule

def test_state_management(console: Console, endpoint: Endpoint, model_id: str):
    """
    Demonstrates saving the state of a group mid-task and resuming it.
    """
    console.print(Rule("[bold magenta]Executing Test: State Management (Save & Load)[/]", style="magenta"))
    
    # Use the same travel agency group from the original test for consistency
    planner_agent = Agent(
        name="规划经理",
        description="一个聪明的规划者，负责分解复杂的旅行请求并委派任务给合适的专家。",
        input_parameters=[{"name": "user_request"}],
        tools=[],
        endpoint=endpoint,
        model_id=model_id,
        target_lang='Simplified Chinese'
    )
    weather_agent = Agent(
        name="天气专员",
        description="专门查询特定城市的天气信息。",
        input_parameters=[{"name": "location"}],
        tools=[Tool(lambda location: f"{location}的天气是20度。")],
        endpoint=endpoint,
        model_id=model_id,
        target_lang='Simplified Chinese'
    )

    travel_agency = Group(
        name="Travel_Agency",
        agents=[planner_agent, weather_agent],
        manager_agent_name="规划经理",
        mode='manager_delegation'
    )

    # 1. Run the group for a few steps and then stop
    console.print("[bold cyan]第一步: 运行部分群组任务...[/]")
    event_stream = travel_agency.run(stream=True, user_request="伦敦的天气怎么样？")
    
    step_count = 0
    for event in event_stream:
        print_event(event, console)
        if event.type == 'step':
            step_count += 1
        if step_count >= 2: # Stop after 2 steps
            break
    
    # 2. Save the state
    state_file = "travel_agency_state.json"
    travel_agency.save_state(state_file)
    console.print(Rule(f"[bold yellow]State saved to {state_file}[/]", style="yellow"))
    
    time.sleep(2) # Pause for dramatic effect

    # 3. Create a new group instance and load the state
    console.print("\n[bold cyan]第二步: 创建新群组并加载状态以继续...[/]")
    
    restored_agency = Group(
        name="恢复的旅行社",
        agents=[planner_agent, weather_agent], # 必须使用相同的配置
        manager_agent_name="规划经理",
        mode='manager_delegation'
    )
    restored_agency.load_state(state_file)
    console.print("State loaded. Resuming the task...")

    # 3. Continue the run. The group should now pick up where it left off.
    resumed_event_stream = restored_agency.run(stream=True) # No kwargs needed to resume
    
    resumed_step_count = 0
    final_answer_found = False
    for event in resumed_event_stream:
        print_event(event, console)
        if event.type == 'step':
            resumed_step_count += 1
        if event.type == 'end' and event.payload.get('result'):
            final_answer_found = True
            console.print(f"[bold green]Final Answer from Resumed Run: {event.payload['result']}[/]")

    # 4. Verification
    if resumed_step_count > 0 and final_answer_found:
        console.print("[bold green]Verification successful: The task resumed and completed.[/]")
    else:
        console.print("[bold red]Verification failed: The task did not appear to resume correctly.[/]")

    # 4. Clean up the state file
    os.remove(state_file)
    console.print(f"Cleaned up state file: {state_file}")
    console.print("[bold green]State Management test finished.[/]")


def main():
    load_dotenv()
    
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    model_id = os.getenv("MODEL_ID")

    if not api_key or not base_url or not model_id:
        raise ValueError("API_KEY, BASE_URL, and MODEL_ID must be set in the .env file.")

    endpoint = Endpoint(api_key=api_key, base_url=base_url)
    console = Console()

    # --- Run Tests ---
    test_state_management(console, endpoint, model_id)

if __name__ == "__main__":
    main()
