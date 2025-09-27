from .agent  import Agent
from .schema import Endpoint
from .event  import pass_event
import os


class OptimizerAgent:
    def __init__(self, endpoint: Endpoint, model_id: str, enable_template_format: bool = False, target_lang: str = "the user's language"):
        self.endpoint = endpoint
        self.model_id = model_id
        self.enable_template_format = enable_template_format
        self.agent: Agent = None
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
        result = pass_event(self.agent.run(prompt=prompt))
        return result.payload.get("final_answer")
