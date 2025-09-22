[中文](./README_zh.md)

# AgentFrame

AgentFrame is a lightweight, event-driven Python framework for building and orchestrating multi-agent systems. It provides simple yet powerful abstractions to create individual agents, equip them with tools, and make them collaborate in groups to solve complex tasks.

## Core Features

- **Modular Agents**: Define autonomous agents with distinct roles, tools, and configurations.
- **Simple Tool Integration**: Easily wrap any Python function into a `Tool` that agents can use.
- **Collaborative Groups**: Orchestrate multiple agents in a `Group`, enabling them to delegate tasks to each other.
- **Flexible Communication Patterns**: Control how agents interact within a group using modes like `broadcast` or `manager_delegation`.
- **Event-Driven & Streamable**: The entire execution process is a stream of `Event` objects, providing full transparency and making it easy to build real-time UIs and logs.
- **Prompt Templating**: Customize agent behavior using Jinja2 templates for system prompts.

## Installation

Clone the repository and install the package in editable mode:

```bash
git clone https://github.com/A03HCY/AgentFrame.git
cd AgentFrame
pip install -e .
```

## Quick Start

### 1. Creating a Single Agent

You can easily create a standalone agent and equip it with tools.

```python
from agentframe import Agent, Tool, Endpoint

# Define a simple function to be used as a tool
def get_current_weather(location: str):
    """Gets the current weather for a specified location."""
    return f"Weather in {location}: 15 degrees Celsius, sunny."

# Create an endpoint configuration
openai_endpoint = Endpoint(
    api_key='YOUR_API_KEY',
    base_url='YOUR_API_BASE_URL'
)

# Create a tool from the function
weather_tool = Tool(get_current_weather)

# Create an agent
weather_agent = Agent(
    name="Weather_Specialist",
    description="Specializes in fetching weather information for a given city.",
    input_parameters=[{"name": "city"}],
    tools=[weather_tool],
    endpoint=openai_endpoint,
    model_id='your-model-id',
    target_lang='English' # Specify the output language
)

# Run the agent and stream events
event_stream = weather_agent.run(stream=True, city="Beijing")
for event in event_stream:
    print(event)
```

### 2. Building a Multi-Agent Team (Group)

The true power of AgentFrame lies in making agents collaborate. Here's how to build a "Travel Agency" team where a manager delegates tasks to specialists.

```python
from agentframe import Agent, Group, Tool, Endpoint

# (Define get_current_weather, find_tourist_attractions, etc.)
# (Create weather_agent, search_agent, etc.)

# Create a manager agent that has no tools of its own
planner_agent = Agent(
    name="Planner_Manager",
    description="A smart planner that breaks down complex travel requests and delegates tasks to the appropriate specialist.",
    input_parameters=[{"name": "user_request"}],
    tools=[], # The manager delegates, it doesn't work
    endpoint=openai_endpoint,
    model_id='your-model-id'
)

# A shared tool available to all agents in the group
shared_flight_tool = Tool(get_flight_info)

# Assemble the team in "manager_delegation" mode
travel_agency = Group(
    name="Travel_Agency",
    agents=[planner_agent, weather_agent, search_agent],
    manager_agent_name="Planner_Manager",
    shared_tools=[shared_flight_tool],
    mode='manager_delegation' # Only the manager can call other agents
)

# Run the entire group on a complex query
user_query = "I want to travel to Beijing. How is the weather, what are the famous attractions, and can you check flight info?"
event_stream = travel_agency.run(stream=True, user_request=user_query)

for event in event_stream:
    print(event)
```

## Key Concepts

### Agent

The `Agent` is the fundamental actor in the system. It is initialized with:
- `name`: A unique identifier.
- `description`: High-level mission objective.
- `input_parameters`: The schema for its main task input.
- `tools`: A list of `Tool` objects it can use.
- `endpoint` & `model_id`: Configuration for the LLM it should use.

### Group

A `Group` coordinates a list of `Agent` instances. Key parameters:
- `agents`: The list of agents in the group.
- `manager_agent_name`: The name of the agent that acts as the entry point for tasks.
- `shared_tools`: A list of `Tool` objects that all agents in the group can access, in addition to their own.
- `mode`:
    - `'broadcast'` (default): Every agent can call every other agent in the group.
    - `'manager_delegation'`: Only the manager agent can call other agents. Specialist agents can only use their own tools and the shared tools.

## Understanding the Event Stream

When you run an agent or group with `stream=True`, the framework returns an iterator of `Event` objects. Each event provides a real-time glimpse into the agent's execution cycle. This is incredibly useful for building UIs, logging, or debugging.

Each `Event` has a `source` (e.g., `Agent:Weather_Specialist`), a `type`, and a `payload`. Here are the key event types you will encounter:

-   **`start`**: Fired once when the agent's task begins.
    -   *Payload*: The initial input parameters given to the agent.
-   **`step`**: Marks the beginning of a new "Think-Act" cycle.
    -   *Payload*: Contains the `current_step` number.
-   **`reasoning_stream`**: A continuous stream of the agent's thought process as it decides what to do next.
    -   *Payload*: A `content` chunk from the LLM's reasoning.
-   **`content_stream`**: A stream of the final answer content, if the LLM decides to respond directly without calling a tool.
    -   *Payload*: A `content` chunk of the final answer.
-   **`decision`**: Fired when the agent has made a firm decision to call a tool or another agent.
    -   *Payload*: Contains the `tool_name` and `tool_args` for the call.
-   **`tool_result`**: Fired after a tool has been executed.
    -   *Payload*: Contains the `tool_name` and the `output` returned by the tool.
-   **`end`**: The final event, signaling that the task is complete.
    -   *Payload*: Contains the `final_answer` or an `error` message if the task failed.
-   **`error`**: Fired if a critical error occurs that terminates the process.
    -   *Payload*: An error `message`.

## Advanced: Customizing Agent Behavior with Prompts

AgentFrame uses a powerful prompt templating system based on Jinja2 to define the core behavior and reasoning process of an agent. The default prompt is located at `agentframe/prompts/default_agent_prompt.md`, which instructs the agent to follow a `Think-Act` cycle.

You can customize this behavior by creating your own prompt template and passing its file path to the `Agent` constructor.

### Default Prompt (`default_agent_prompt.md`)

The default template establishes a "Cognitive Framework" for the agent, guiding it to:
1.  **OBSERVE**: Review the objective and current state.
2.  **THINK**: Assess information, plan the next step, and select a tool or expert agent.
3.  **ACT**: Externalize its thought process and execute the chosen action.

This structured approach ensures transparent and logical decision-making.

### Using a Custom Prompt Template

To override the default behavior, simply provide the path to your custom `.md` template file when creating an agent:

```python
my_custom_prompt_path = "path/to/your/custom_prompt.md"

custom_agent = Agent(
    name="Custom_Agent",
    # ... other parameters
    prompt_template_path=my_custom_prompt_path
)
```

This allows you to completely redefine the agent's operational guidelines, personality, or even its reasoning structure.

### Template Variables

When creating a custom prompt, you can use the following Jinja2 variables, which are passed to the template automatically:

-   `{{ agent_name }}`: The name of the agent.
-   `{{ agent_description }}`: The high-level mission description for the agent.
-   `{{ target_language }}`: The desired output language for the agent's responses (e.g., 'English', 'Simplified Chinese').
-   `{{ plain_tools }}`: A list of standard `Tool` objects available to the agent. These are regular Python functions.
-   `{{ agent_tools }}`: A list of tools that are actually other agents. This allows you to show them differently in the prompt, for instance, as "Expert Agents".
-   `{{ tools }}`: The complete list of all tools (both `plain_tools` and `agent_tools`).

You can iterate over these tool lists in your template to dynamically display the agent's capabilities, like this:

```jinja
--- FOUNDATIONAL TOOLS ---
{% for tool in plain_tools %}
**- {{ tool.name }}({% for p in tool.parameters %}{{ p.name }}: {{ p.get('annotation', 'any')}}{% if not loop.last %}, {% endif %}{% endfor %})**
  *Function*: {{ tool.description | indent(4) }}
{% endfor %}
```
