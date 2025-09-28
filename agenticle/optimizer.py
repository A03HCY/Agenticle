from .agent  import Agent
from .schema import Endpoint
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
        if not self.agent:
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
        if not self.agent:
            self.init()
        return self.agent.run(stream=False, prompt=prompt)
