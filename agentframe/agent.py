import os
import json
import jinja2
from openai import OpenAI
from typing import List, Dict, Any, Optional

from .schema import Endpoint
from .tool import Tool

class Agent:
    def __init__(
        self,
        name: str,
        description: str,
        input_parameters: List[Dict[str, Any]],
        tools: List[Tool],
        endpoint: Endpoint,
        prompt_template_path: Optional[str] = None, # 接受模板文件路径
        max_steps: int = 10
    ):
        self.name = name
        self.description = description
        self.input_parameters = input_parameters
        
        self.endpoint = endpoint
        self.max_steps = max_steps
        self._client = OpenAI(api_key=endpoint.api_key, base_url=endpoint.base_url)

        self.tools: Dict[str, Tool] = {tool.name: tool for tool in tools}

        self._api_tools: List[Dict[str, Any]] = [t.info for t in self.tools.values()]
        
        self.system_prompt: str = self._generate_system_prompt_from_template(prompt_template_path)
        
        self.history: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]

    def _generate_system_prompt_from_template(self, template_path: Optional[str]) -> str:
        """从 Jinja2 模板文件加载并渲染系统提示。"""
        
        # 如果没有提供模板路径，就使用一个默认的硬编码路径
        if template_path is None:
            # 假设模板文件与 agent.py 在同一目录下的 prompts/ 文件夹中
            current_dir = os.path.dirname(os.path.abspath(__file__))
            template_path = os.path.join(current_dir, 'prompts', 'default_agent_prompt.md')
        try:
            # 设置 Jinja2 环境，从文件系统加载模板
            template_dir = os.path.dirname(template_path)
            template_filename = os.path.basename(template_path)
            
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(template_dir),
                trim_blocks=True, # 自动移除模板标签后的第一个换行符
                lstrip_blocks=True # 自动移除模板标签前的空格
            )
            
            template = env.get_template(template_filename)
        except jinja2.TemplateNotFound:
            raise FileNotFoundError(f"Prompt template not found at: {template_path}")
        
        # 准备要传递给模板的数据
        template_data = {
            "agent_name": self.name,
            "agent_description": self.description,
            "tools": list(self.tools.values()) # 传递完整的 Tool 对象列表
        }
        
        # 渲染模板
        return template.render(template_data)

    def _execute_tool(self, tool_call: Dict[str, Any]) -> Any:
        tool_name = tool_call.function.name
        tool_to_run = self.tools.get(tool_name)
        
        if not tool_to_run:
            return f"Error: Tool '{tool_name}' not found."
            
        try:
            tool_args = json.loads(tool_call.function.arguments)
            return tool_to_run.execute(**tool_args)
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

    def run(self, **kwargs) -> str:
        """
        运行 Agent 的主循环。接受启动参数。
        """
        # 1. 构造初始输入
        initial_prompt = (
            "Task started. Here are your input parameters:\n"
            + json.dumps(kwargs, indent=2)
            + "\nNow, begin your work."
        )
        self.history.append({"role": "user", "content": initial_prompt})

        # 2. “思考-行动”循环
        for step in range(self.max_steps):
            print(f"--- [Agent: {self.name}] Step {step + 1} ---")
            
            response = self._client.chat.completions.create(
                model="gpt-4-turbo",
                messages=self.history,
                tools=self._api_tools,
                tool_choice="auto"
            )
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                self.history.append(response_message)
                
                # 特殊处理 end_task
                tool_call = response_message.tool_calls[0]
                if tool_call.function.name == "end_task":
                    print(f"Decision: Agent '{self.name}' is ending the task.")
                    task_result = json.loads(tool_call.function.arguments)
                    return task_result.get("final_answer", "Task ended without a clear answer.")

                print(f"Decision: Call tool '{tool_call.function.name}'")
                tool_output = self._execute_tool(tool_call)
                
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": str(tool_output)
                })
                continue
            else:
                # 如果 LLM 不调用任何工具而是直接回复，我们将其添加历史并继续循环，
                # 强制它最终必须调用 end_task
                print("Decision: Thinking...")
                self.history.append({"role": "assistant", "content": response_message.content})
                continue
        
        return f"Error: Agent '{self.name}' failed to complete the task within {self.max_steps} steps."

    def as_tool(self) -> Tool:
        """
        将整个 Agent 实例包装成一个 Tool，使其可以被其他 Agent 调用。
        """
        # 动态创建一个包装函数
        def agent_runner(**kwargs):
            # 每次调用时，都创建一个新的 Agent 实例以保证状态隔离
            agent_instance = Agent(
                name=self.name,
                description=self.description,
                input_parameters=self.input_parameters,
                tools=list(self.tools.values()),
                endpoint=self.endpoint,
                max_steps=self.max_steps
            )
            return agent_instance.run(**kwargs)

        # 伪造一个函数，以便 Tool 类可以解析它
        # 这一步有点 hacky，但非常有效
        agent_runner.__name__ = self.name
        agent_runner.__doc__ = self.description
        
        # 动态构建函数签名
        from inspect import Parameter, Signature
        params = [
            Parameter(name=p['name'], kind=Parameter.POSITIONAL_OR_KEYWORD) 
            for p in self.input_parameters
        ]
        agent_runner.__signature__ = Signature(params)

        return Tool(func=agent_runner)

    def reset(self):
        self.history = [{"role": "system", "content": self.system_prompt}]
