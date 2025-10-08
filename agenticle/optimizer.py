from .agent  import Agent
from .schema import Endpoint
from .tool   import Tool
from .utils  import model_id
import os
from typing import List

class BaseOptimizer:
    """Base class for all optimizers."""
    def __init__(self, endpoint: Endpoint = Endpoint(), model_id: str = model_id):
        self.endpoint = endpoint
        self.model_id = model_id
        self.agent: Agent = None

    def init(self, **kwargs):
        """Initializes the internal agent of the optimizer."""
        raise NotImplementedError

    def optimize(self, *args, **kwargs) -> str:
        """Runs the optimization process."""
        raise NotImplementedError

class CompetitionOptimizer(BaseOptimizer):
    """
    An optimizer that uses an agent to select the best result from a list of competing results.
    """
    def __init__(self, endpoint: Endpoint = Endpoint(), model_id: str = model_id):
        super().__init__(endpoint, model_id)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_path = os.path.join(current_dir, 'prompts', 'competition_opt_prompt.md')

    def init(self):
        """Initializes the competition optimizer agent."""
        self.agent = Agent(
            name="CompetitionOptimizer",
            description="An expert evaluator that analyzes multiple solutions to a problem and determines the best one.",
            input_parameters=[
                {"name": "task_description", "description": "The original task description."},
                {"name": "results", "description": "A list of results from different agents."}
            ],
            tools=[],
            endpoint=self.endpoint,
            model_id=self.model_id,
            prompt_template_path=self.template_path,
        )

    def optimize(self, task_description: str, results: List[str]) -> str:
        """
        Analyzes a list of results and returns the best one.

        Args:
            task_description (str): The original task description given to the competing agents.
            results (List[str]): A list of final answers from the competing agents.

        Returns:
            str: The selected best result.
        """
        self.init()
        
        # The results are formatted as a numbered list for the prompt.
        formatted_results = "\n".join(f"{i+1}. {result}" for i, result in enumerate(results))
        
        return self.agent.run(
            stream=False, 
            task_description=task_description, 
            results=formatted_results
        )

class PromptOptimizer(BaseOptimizer):
    def __init__(self, endpoint: Endpoint = Endpoint(), model_id: str = model_id, enable_template_format: bool = False, target_lang: str = "the user's language"):
        super().__init__(endpoint, model_id)
        self.enable_template_format = enable_template_format
        self.target_lang = target_lang
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_path = os.path.join(current_dir, 'prompts', 'opt_prompt.md')

    def init(self):
        target_lang = f"a Jinja2 template format in {self.target_lang}" if self.enable_template_format else self.target_lang
        self.agent = Agent(
            name="PromptOptimizer",
            description="An expert in prompt engineering that refines and enhances "
            "user-provided prompts to make them clearer, more specific, "
            "and more effective for Large Language Models.",
            input_parameters=[{"name": "prompt"}],
            tools=[],
            endpoint=self.endpoint,
            model_id=self.model_id,
            prompt_template_path=self.template_path,
            target_lang=target_lang,
        )

    def optimize(self, prompt: str) -> str:
        self.init()
        return self.agent.run(stream=False, prompt=prompt)

class NaturalLanguageOptimizer(BaseOptimizer):
    """
    Generates a full agent or group YAML configuration from a brief natural language requirement
    using a two-step brainstorming and formatting process.
    """
    def __init__(self, endpoint: Endpoint = Endpoint(), model_id: str = model_id):
        super().__init__(endpoint, model_id)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.brainstorm_template_path = os.path.join(current_dir, 'prompts', 'brainstorm_prompt.md')
        self.format_template_path = os.path.join(current_dir, 'prompts', 'format_prompt.md')
        
        self.brainstorm_agent: Agent = None
        self.format_agent: Agent = None

    def init(self, tools: List[Tool] = []):
        """Initializes the internal agents."""
        self.brainstorm_agent = Agent(
            name="BrainstormingAgent",
            description="A creative expert in designing AI agent teams.",
            input_parameters=[
                {"name": "requirement", "description": "The user's brief requirement."},
                {"name": "entity_type", "description": "The type of entity to create ('Agent' or 'Group')."}
            ],
            tools=[],
            endpoint=self.endpoint,
            model_id=self.model_id,
            prompt_template_path=self.brainstorm_template_path,
        )
        
        self.format_agent = Agent(
            name="FormattingAgent",
            description="A YAML formatting expert.",
            input_parameters=[
                {"name": "brainstorming_plan", "description": "The unstructured brainstorming plan."}
            ],
            tools=[],
            endpoint=self.endpoint,
            model_id=self.model_id,
            prompt_template_path=self.format_template_path,
        )
        
        available_tools_str = "\n".join(
            f'- `{tool.name}`: {tool.description}' for tool in tools
        ) if tools else "No external tools provided."

        self.brainstorm_agent._configure_with_tools(
            tools=[],
            extra_context={"available_tools": available_tools_str}
        )

    def optimize(self, requirement: str, tools: List[Tool] = [], group: bool = False) -> str:
        """
        Generates a full, well-formatted YAML configuration from a brief requirement.
        """
        self.init(tools=tools)
        entity_type = "Group" if group else "Agent"

        # Step 1: Brainstorm the configuration
        brainstorming_plan = self.brainstorm_agent.run(
            stream=False,
            requirement=requirement,
            entity_type=entity_type
        )

        # Step 2: Format the brainstormed plan into YAML
        raw_yaml = self.format_agent.run(
            stream=False,
            brainstorming_plan=brainstorming_plan
        )
        
        # Clean the output by removing markdown fences
        return raw_yaml.strip().replace("```yaml", "").replace("```", "").strip()
