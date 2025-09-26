import os
import json
from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.utils import print_event
from agenticle import Agent, Group, Endpoint

def create_voter_agent(name: str, personality: str, endpoint: Endpoint, model_id: str) -> Agent:
    """Creates a voter agent with a specific personality."""
    return Agent(
        name=name,
        description=f"An agent with a personality: {personality}",
        input_parameters=[
            {"name": "task", "type": "string"},
            {"name": "options", "type": "dict"}
        ],
        tools=[], # Voters don't need tools, they just decide
        endpoint=endpoint,
        model_id=model_id,
        optimize_tool_call=True
    )

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

    # --- 1. Create Voter Agents with different personalities ---
    cautious_agent = create_voter_agent(
        "Cautious_Voter",
        "You are very cautious and prefer the safest option.",
        openai_endpoint,
        model_id
    )
    
    adventurous_agent = create_voter_agent(
        "Adventurous_Voter",
        "You are adventurous and prefer the most exciting option.",
        openai_endpoint,
        model_id
    )

    analytical_agent = create_voter_agent(
        "Analytical_Voter",
        "You are very analytical and prefer the most logical and well-reasoned option.",
        openai_endpoint,
        model_id
    )

    # --- 2. Form a Group in Voting Mode ---
    decision_committee = Group(
        name="Decision_Committee",
        agents=[cautious_agent, adventurous_agent, analytical_agent],
        mode='voting'
    )

    # --- 3. Run a Voting Task ---
    task_prompt = "We need to decide on a new feature for our app. Which one should we prioritize?"
    voting_options = {
        "feature_A": "A stable, low-risk feature that slightly improves user experience.",
        "feature_B": "A high-risk, high-reward experimental feature that could be a game-changer.",
    }

    console.print(Rule(f"[bold]Executing Voting Task for Group: {decision_committee.name}[/]", style="cyan"))
    
    # The final result is not streamed, but we can see the events
    event_stream = decision_committee.run(stream=True, task=task_prompt, options=voting_options, retries=3)

    final_payload = {}
    for event in event_stream:
        print_event(event, console)
        if event.type == "end":
            final_payload = event.payload

    console.print(Rule("[bold]Voting Finished[/]", style="cyan"))
    
    # --- 4. Display Final Results ---
    console.print(f"\n[bold]Winning Vote:[/bold] {final_payload.get('result')}")
    console.print("\n[bold]Voting Breakdown:[/bold]")
    
    details = final_payload.get('details', {})
    vote_counts = details.get('vote_counts', {})
    all_votes = details.get('all_votes', [])

    for option, count in vote_counts.items():
        console.print(f"- {option}: {count} vote(s)")

    console.print("\n[bold]Individual Votes & Reasons:[/bold]")
    for vote in all_votes:
        console.print(f"- [bold]{vote['agent']}[/bold] voted for [green]{vote['vote']}[/green] because: \"{vote['reason']}\"")

if __name__ == "__main__":
    main()
