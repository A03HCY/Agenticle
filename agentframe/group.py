from typing import List, Dict, Any, Union, Iterator, Optional

from .agent import Agent
from .tool import Tool
from .event import Event

class Group:
    """
    一个 Agent 团队，可以协作完成复杂的任务。
    
    Group 包含一组 Agent。它会自动进行“布线”，使每个 Agent
    都能将团队中的其他 Agent 视为可以调用的专家工具。
    """

    def __init__(
        self,
        name: str,
        agents: List[Agent],
        manager_agent_name: Optional[str] = None,
        shared_tools: Optional[List[Tool]] = None,
        mode: str = 'broadcast'
    ):
        """
        初始化一个 Agent Group。

        Args:
            name (str): 团队的名称。
            agents (List[Agent]): 团队中的 Agent 实例列表。
            manager_agent_name (str, optional): 指定的管理者 Agent 的名称。
                                                如果未提供，将使用列表中的第一个 Agent。
            shared_tools (Optional[List[Tool]], optional): 团队共享的工具列表。
            mode (str, optional): Agent 间的通信模式。
                                  'broadcast': 所有 Agent 都可以互相调用。
                                  'manager_delegation': 只有管理者可以调用其他 Agent。
        """
        self.name = name
        self.agents: Dict[str, Agent] = {agent.name: agent for agent in agents}
        self.shared_tools = shared_tools or []
        self.mode = mode

        if not agents:
            raise ValueError("Group must contain at least one agent.")

        # 确定管理者 (Manager Agent)
        if manager_agent_name:
            if manager_agent_name not in self.agents:
                raise ValueError(f"Manager agent '{manager_agent_name}' not found in the group.")
            self.manager_agent = self.agents[manager_agent_name]
        else:
            self.manager_agent = list(self.agents.values())[0]  # 默认第一个为管理者
        
        # 核心：自动布线，让 Agent 互相认识
        self._wire_agents()

    def _wire_agents(self):
        """
        根据设定的模式，配置团队中每个 Agent 的工具集。
        """
        all_agents_as_tools = {name: agent.as_tool() for name, agent in self.agents.items()}

        for agent_name, agent in self.agents.items():
            final_toolset = []
            
            # 1. 添加 Agent 自己的原生工具
            if hasattr(agent, 'original_tools'):
                final_toolset.extend(agent.original_tools)
            
            # 2. 添加团队共享工具
            final_toolset.extend(self.shared_tools)

            # 3. 根据模式添加其他 Agent 作为工具
            is_manager = (agent_name == self.manager_agent.name)

            if self.mode == 'broadcast' or (self.mode == 'manager_delegation' and is_manager):
                # 广播模式下所有 Agent 或 委派模式下的管理者，可以调用其他 Agent
                for other_name, other_agent_as_tool in all_agents_as_tools.items():
                    if agent_name != other_name:
                        final_toolset.append(other_agent_as_tool)
            
            # 4. 更新 Agent 的配置
            agent._configure_with_tools(final_toolset)
            # print(f"Agent '{agent_name}' reconfigured with tools: {[t.name for t in final_toolset]}")


    def run(self, stream: bool = False, **kwargs) -> Union[str, Iterator[Event]]:
        """
        运行整个 Group 来执行一个任务。
        任务将首先被传递给管理者 Agent。

        Args:
            stream (bool): 如果为 True，则返回一个事件生成器进行实时输出。
                           如果为 False，则阻塞直到任务完成并返回最终字符串。
            **kwargs: 启动管理者 Agent 所需的输入参数。

        Returns:
            Union[str, Iterator[Event]]: 最终结果或事件流。
        """
        if stream:
            return self._run_stream(**kwargs)
        else:
            # 对于非流式，直接调用管理者的非流式 run 方法
            return self.manager_agent.run(stream=False, **kwargs)

    def _run_stream(self, **kwargs) -> Iterator[Event]:
        """【核心】作为事件生成器运行 Group 的主循环。"""
        
        # 1. 发出 Group 开始的信号
        yield Event(f"Group:{self.name}", "start", {"manager": self.manager_agent.name, "input": kwargs})

        # 2. 获取并启动管理者 Agent 的事件流
        manager_stream = self.manager_agent.run(stream=True, **kwargs)
        
        final_result = f"Group '{self.name}' finished without a clear final answer."

        # 3. 迭代管理者的流，并将所有事件（包括它调用的子 Agent 的事件）实时传递出去
        for event in manager_stream:
            # 4. 捕获管理者 Agent 自己的结束信号，以获取最终结果
            if event.source == f"Agent:{self.manager_agent.name}" and event.type == "end":
                final_result = event.payload.get("final_answer", final_result)
            
            # 5. 将所有事件（无论来源）都直接转发出去
            yield event
        
        # 6. 在所有流程结束后，发出 Group 结束的信号
        yield Event(f"Group:{self.name}", "end", {"result": final_result})
