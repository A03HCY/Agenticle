from agenticle import Event
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
    elif event.type == "resume":
        console.print(
            Panel(
                f"Resuming from a history of {event.payload.get('history_length', 'N/A')} messages.",
                title=f"🔄 [bold]{source_name} Resumed[/]",
                border_style=base_style,
                expand=False
            )
        )
    elif event.type == "step":
        step_info = event.payload.get('current_step') or event.payload.get('step')
        agent_name_info = f" ({event.payload.get('agent_name')})" if event.payload.get('agent_name') else ""
        console.print(Rule(f"{event.source}{agent_name_info} Step {step_info}", style=base_style))
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
        # Fallback for any other event types
        console.rule(f"Unknown Event: {event.type}", style="red")
        console.print(event.payload)
