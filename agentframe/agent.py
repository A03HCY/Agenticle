import os
import json
import jinja2
from openai import OpenAI
from typing import List, Dict, Any, Optional, Union, Iterator

from .schema import Endpoint
from .tool import Tool, EndTaskTool
from .event import Event, EventBroker

class Agent:
    def __init__(
        self,
        name: str,
        description: str,
        input_parameters: List[Dict[str, Any]],
        tools: List[Tool],
        endpoint: Endpoint,
        model_id: str,
        event_broker: EventBroker = EventBroker(),
        prompt_template_path: Optional[str] = None,
        target_lang:str = 'en',
        max_steps: int = 10
    ):
        self.name = name
        self.description = description
        self.input_parameters = input_parameters
        self.model_id = model_id

        self.target_lang = target_lang
        self.event_broker = event_broker

        os.environ['OPENAI_API_KEY'] = endpoint.api_key
        
        self.endpoint = endpoint
        self.max_steps = max_steps
        self._client = OpenAI(api_key=endpoint.api_key, base_url=endpoint.base_url)

        self.original_tools: List[Tool] = tools[:]
        self.tools: Dict[str, Tool] = {tool.name: tool for tool in tools}
        
        if "end_task" in self.tools:
            print("Warning: A user-provided tool named 'end_task' is being overridden by the built-in final answer tool.")
        # 2. 无论如何，都内置我们标准的 EndTaskTool
        self.tools["end_task"] = EndTaskTool()

        self._api_tools: List[Dict[str, Any]] = [t.info for t in self.tools.values()]
        
        self.system_prompt: str = self._generate_system_prompt_from_template(prompt_template_path)
        
        self.history: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
    
    def _configure_with_tools(self, tools: List[Tool]):
        """用给定的工具列表重新配置 Agent。"""
        self.tools = {tool.name: tool for tool in tools}
        if not "end_task" in self.tools:
            self.tools["end_task"] = EndTaskTool() # 确保 end_task 始终存在
        
        # 重新生成 API tools 和 system prompt
        self._api_tools = [t.info for t in self.tools.values()]
        self.system_prompt = self._generate_system_prompt_from_template(
            getattr(self, '_prompt_template_path', None)
        )
        self.reset() # 重置历史以应用新的系统提示


    def _generate_system_prompt_from_template(self, template_path: Optional[str] = None) -> str:
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
        
        plain_tools = []
        agent_tools = []
        for tool in self.tools.values():
            if getattr(tool, 'is_agent_tool', False):
                agent_tools.append(tool)
            else:
                plain_tools.append(tool)

        # 准备要传递给模板的数据
        template_data = {
            "agent_name": self.name,
            "agent_description": self.description,
            "plain_tools": plain_tools, # 传递普通工具
            "agent_tools": agent_tools, # 传递 Agent 工具
            "tools": list(self.tools.values()), # 仍然传递完整的工具列表以备后用
            "target_language": "Simplified Chinese"
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

    def run(self, stream: bool = False, **kwargs) -> Union[str, Iterator[Event]]:
        """
        运行 Agent 的主循环。
        Args:
            stream (bool): 如果为 True，则返回一个事件生成器进行实时输出。
                           如果为 False，则阻塞直到任务完成并返回最终字符串。
            **kwargs: 启动 Agent 所需的输入参数。
        Returns:
            Union[str, Iterator[Event]]: 最终结果或事件流。
        """
        if stream:
            return self._run_stream(**kwargs)
        else:
            # 对于非流式，我们可以在内部模拟一个简单的事件处理器
            final_answer = ""
            for event in self._run_stream(**kwargs):
                if event.type == "end":
                    final_answer = event.payload.get("final_answer", "")
            return final_answer
    def _run_stream(self, **kwargs) -> Iterator[Event]:
        """【核心】作为事件生成器运行 Agent 的主循环。"""
        # 重置历史记录以进行新的运行
        self.reset()
        
        # 1. 构造初始输入并 yield 开始事件
        initial_prompt = (
            "Task started. Here are your input parameters:\n"
            + json.dumps(kwargs, indent=2)
            + "\nNow, begin your work."
        )
        self.history.append({"role": "user", "content": initial_prompt})
        yield Event(f"Agent:{self.name}", "start", kwargs)
        # 2. “思考-行动”循环
        for step in range(self.max_steps):
            yield Event(f"Agent:{self.name}", "step", {"current_step": step + 1})
            # 3. 思考 (Think): 以流式调用 LLM
            response_stream = self._client.chat.completions.create(
                model=self.model_id,
                messages=self.history,
                tools=self._api_tools,
                tool_choice="auto",
                stream=True
            )
            # 4. 从流中重新组装响应
            full_response_content = ""
            full_reasoning_content = ""
            tool_calls_in_progress = [] # 用于组装工具调用
            for chunk in response_stream:
                try:
                    delta = chunk.choices[0].delta
                except:
                    continue
                
                # a. 处理流式文本内容 (思考过程或最终答案)
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    full_reasoning_content += delta.reasoning_content
                    yield Event(f"Agent:{self.name}", "reasoning_stream", {"content": delta.reasoning_content})
                
                if delta.content:
                    full_response_content += delta.content
                    yield Event(f"Agent:{self.name}", "content_stream", {"content": delta.content})
                # b. 处理流式工具调用
                if delta.tool_calls:
                    for tool_call_chunk in delta.tool_calls:
                        # 如果是新的工具调用
                        if tool_call_chunk.index >= len(tool_calls_in_progress):
                            tool_calls_in_progress.append(tool_call_chunk.function)
                        else: # 否则，累加参数
                            func = tool_calls_in_progress[tool_call_chunk.index]
                            if tool_call_chunk.function.name:
                                func.name = (func.name or "") + tool_call_chunk.function.name
                            if tool_call_chunk.function.arguments:
                                func.arguments = (func.arguments or "") + tool_call_chunk.function.arguments
                        # 实时 yield 工具调用构建过程
                        yield Event(f"Agent:{self.name}", "tool_call_stream", {"index": tool_call_chunk.index, "delta": tool_call_chunk.function.dict()})
            # 组装完整的消息以添加到历史记录
            assembled_message = {"role": "assistant"}
            if full_response_content:
                assembled_message["content"] = full_response_content
            if tool_calls_in_progress:
                # 注意: OpenAI SDK 在组装时需要完整的 tool_calls 结构
                assembled_message["tool_calls"] = [{"id": f"call_{i}", "type": "function", "function": func.dict()} for i, func in enumerate(tool_calls_in_progress)]
                # 为 tool_calls 伪造一个 ID，因为流式响应不提供它
                # 但我们需要它来匹配 tool_result
            
            self.history.append(assembled_message)
            # 5. 决策和行动
            if tool_calls_in_progress:
                # 遍历所有工具调用
                for tool_call_data in assembled_message["tool_calls"]:
                    tool_name = tool_call_data['function']['name']
                    
                    # a. 特殊处理 end_task
                    if tool_name == "end_task":
                        task_result = json.loads(tool_call_data['function']['arguments'])
                        yield Event(f"Agent:{self.name}", "end", task_result)
                        return # 结束生成器

                    # b. 执行常规工具或 Agent
                    tool_args = json.loads(tool_call_data['function']['arguments'])
                    yield Event(f"Agent:{self.name}", "decision", {"tool_name": tool_name, "tool_args": tool_args})
                    
                    tool_call_id = tool_call_data['id']
                    
                    # 执行工具并处理可能的事件流
                    execution_generator = self._execute_tool_from_dict(tool_call_data)
                    
                    tool_output = ""
                    # 如果是子 Agent，实时转发其事件
                    if isinstance(execution_generator, Iterator):
                        for sub_event in execution_generator:
                            yield sub_event # 实时转发
                            # 捕获子 Agent 的最终答案作为工具输出
                            if sub_event.type == 'end' and sub_event.payload.get('final_answer'):
                                tool_output = sub_event.payload['final_answer']
                    else: # 如果是普通工具
                        tool_output = execution_generator

                    yield Event(f"Agent:{self.name}", "tool_result", {"tool_name": tool_name, "output": tool_output})
                    
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": str(tool_output)
                    })
                continue
            else: # 如果 LLM 没有调用工具，而是直接回复
                yield Event(f"Agent:{self.name}", "thinking", {"content": full_response_content})
                # 我们强制它必须用 end_task 结束，所以继续循环
                continue
        # 如果循环结束仍未完成
        final_message = f"Error: Agent '{self.name}' failed to complete the task within {self.max_steps} steps."
        yield Event(f"Agent:{self.name}", "error", {"message": final_message})
        return
    
    def _execute_tool_from_dict(self, tool_call_dict: Dict) -> Any:
        """
        执行工具。如果工具是 Agent，则返回其事件生成器。
        """
        name = tool_call_dict['function']['name']
        args = json.loads(tool_call_dict['function']['arguments'])
        tool: Optional[Tool] = self.tools.get(name)

        if not tool:
            return f"Error: Tool '{name}' not found."
        
        try:
            # 如果是 Agent 工具，它将返回一个生成器
            if tool.is_agent_tool:
                # 确保以流式模式调用
                return tool.execute(stream=True, **args)
            else: # 否则，它将返回一个直接结果
                return tool.execute(**args)
        except Exception as e:
            return f"Error executing tool '{name}': {e}"

    def as_tool(self) -> Tool:
        """
        将整个 Agent 实例包装成一个 Tool，使其可以被其他 Agent 调用。
        """
        # 动态创建一个包装函数
        def agent_runner(stream: bool = False, **kwargs):
            # 每次调用时，都创建一个新的 Agent 实例以保证状态隔离
            agent_instance = Agent(
                name=self.name,
                description=self.description,
                input_parameters=self.input_parameters,
                tools=self.original_tools, # 确保隔离
                endpoint=self.endpoint,
                model_id=self.model_id,
                max_steps=self.max_steps
            )
            return agent_instance.run(stream=stream, **kwargs)

        # 伪造一个函数，以便 Tool 类可以解析它
        # 这一步有点 hacky，但非常有效
        agent_runner.__name__ = self.name
        agent_runner.__doc__ = f'An Agent: {self.description}'
        
        # 动态构建函数签名
        from inspect import Parameter, Signature
        params = [
            Parameter(name=p['name'], kind=Parameter.POSITIONAL_OR_KEYWORD) 
            for p in self.input_parameters
        ]
        agent_runner.__signature__ = Signature(params)

        return Tool(func=agent_runner, is_agent_tool=True)

    def reset(self):
        self.history = [{"role": "system", "content": self.system_prompt}]
