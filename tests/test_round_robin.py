import os
from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.utils import print_event
from agenticle   import Agent, Group, Endpoint, Workspace

def test_round_robin_with_workspace(console: Console, endpoint: Endpoint, model_id: str):
    """
    Demonstrates the 'round_robin' mode where agents work sequentially
    and collaborate using a shared workspace.
    """
    console.print(Rule("[bold magenta]Executing Test: Round Robin with Workspace[/]", style="magenta"))

    # 1. Create a shared workspace for the agents
    # The workspace will be created in a temporary directory
    shared_workspace = Workspace()
    console.print(f"Workspace created at: {shared_workspace.path}")

    # 2. Define Agents for a content creation pipeline
    writer_agent = Agent(
        name="内容写手",
        description="你的任务是根据所提供的主题，撰写一篇关于AI优势的简短博客文章。请将草稿保存到工作区的 'blog_post.md' 文件中。",
        input_parameters=[{"name": "topic", "description": "博客文章的主题"}],
        tools=[], # 工具由工作空间提供
        endpoint=endpoint,
        model_id=model_id,
        target_lang='Simplified Chinese'
    )

    reviewer_agent = Agent(
        name="内容审阅员",
        description="你的任务是审阅位于 'blog_post.md' 的草稿，提出改进建议，并将最终版本保存为 'blog_post_final.md'。",
        input_parameters=[{"name": "feedback_guideline", "description": "审稿的指导原则"}],
        tools=[], # 工具由工作空间提供
        endpoint=endpoint,
        model_id=model_id,
        target_lang='Simplified Chinese'
    )

    # 3. Create a Group in 'round_robin' mode
    writing_pipeline = Group(
        name="Writing_Pipeline",
        agents=[writer_agent, reviewer_agent],
        mode='round_robin',
        workspace=shared_workspace
    )

    # 4. Run the pipeline
    event_stream = writing_pipeline.run(stream=True, topic="人工智能在创意产业的未来", feedback_guideline="请确保文章风格正式且具有说服力。")
    for event in event_stream:
        print_event(event, console)

    # 5. Clean up the temporary workspace
    console.print(f"Cleaning up workspace: {shared_workspace.path}")
    shared_workspace.cleanup()
    console.print("[bold green]Round Robin test finished.[/]")

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
    test_round_robin_with_workspace(console, endpoint, model_id)

if __name__ == "__main__":
    main()
