[English](./README.md)

# Agenticle

Agenticle 是一个轻量级的、事件驱动的 Python 框架，用于构建和编排多智能体系统。它提供了简单而强大的抽象，用于创建独立的智能体，为它们配备工具，并让它们在群组中协作以解决复杂任务。

## 核心特性

- **模块化智能体**: 定义具有不同角色、工具和配置的自主智能体。
- **简单的工具集成**: 轻松将任何 Python 函数包装成一个智能体可以使用的 `Tool`。
- **外部工具集成 (MCP)**: 通过模型上下文协议 (Model Context Protocol) 连接到外部的、语言无关的工具服务器。
- **协作群组**: 在一个 `Group` 中编排多个智能体，使它们能够相互委派任务。
- **灵活的通信模式**: 使用 `broadcast`、`manager_delegation` 或序列化的 `round_robin` 等模式控制智能体在群组内的交互方式。
- **共享工作空间**: 为群组提供一个沙盒化的文件系统 (`Workspace`)，允许智能体通过读写文件进行协作。
- **状态管理**: 保存和加载整个智能体群组的状态，使得长时任务可以被暂停和恢复。
- **事件驱动与可流式处理**: 整个执行过程是一个 `Event` 对象流，提供了完全的透明度，并使得构建实时用户界面和日志变得容易。
- **动态提示词模板**: 使用 Jinja2 模板为系统提示词定制智能体行为，并能够从群组注入上下文信息。

## 安装

直接从 PyPI 安装包：

```bash
pip install agenticle
```

或者，对于开发，克隆仓库并以可编辑模式安装：

```bash
git clone https://github.com/A03HCY/Agenticle.git
cd Agenticle
pip install -e .
```

## 快速入门

### 1. 创建单个智能体

您可以轻松创建一个独立的智能体并为其配备工具。

```python
from agenticle import Agent, Tool, Endpoint

# 定义一个简单的函数作为工具使用
def get_current_weather(location: str):
    """获取指定地点的当前天气。"""
    return f"{location}的天气：15摄氏度，晴朗。"

# 创建一个端点配置
openai_endpoint = Endpoint(
    api_key='你的API密钥',
    base_url='你的API基础URL'
)

# 从函数创建一个工具
weather_tool = Tool(get_current_weather)

# 创建一个智能体
weather_agent = Agent(
    name="天气专员",
    description="专门为给定城市获取天气信息。",
    input_parameters=[{"name": "city"}],
    tools=[weather_tool],
    endpoint=openai_endpoint,
    model_id='你的模型ID',
    target_lang='Simplified Chinese' # 指定输出语言
)

# 运行智能体并流式传输事件
event_stream = weather_agent.run(stream=True, city="北京")
for event in event_stream:
    print(event)
```

### 2. 构建多智能体团队 (Group)

Agenticle 的真正威力在于让智能体协作。以下是如何构建一个“旅行社”团队，其中管理者将任务委派给专员。

```python
from agenticle import Agent, Group, Tool, Endpoint

# (定义 get_current_weather, find_tourist_attractions 等函数)
# (创建 weather_agent, search_agent 等智能体)

# 创建一个本身没有工具的管理者智能体
planner_agent = Agent(
    name="规划经理",
    description="一个聪明的规划者，能够分解复杂的旅行请求并将任务委派给合适的专员。",
    input_parameters=[{"name": "user_request"}],
    tools=[], # 管理者只委派任务，自己不工作
    endpoint=openai_endpoint,
    model_id='你的模型ID'
)

# 一个群组中所有智能体都可以使用的共享工具
shared_flight_tool = Tool(get_flight_info)

# 以 "manager_delegation" 模式组建团队
travel_agency = Group(
    name="旅行社",
    agents=[planner_agent, weather_agent, search_agent],
    manager_agent_name="规划经理",
    shared_tools=[shared_flight_tool],
    mode='manager_delegation' # 只有管理者可以调用其他智能体
)

# 对一个复杂查询运行整个群组
user_query = "我想去北京旅行。天气怎么样，有哪些著名景点，能帮我查一下航班信息吗？"
event_stream = travel_agency.run(stream=True, user_request=user_query)

for event in event_stream:
    print(event)
```

## 通过 MCP 与外部工具集成

Agenticle 支持 **模型上下文协议 (Model Context Protocol, MCP)**，使智能体能够连接并使用来自外部、语言无关的服务器的工具。这使您能够将智能体的能力扩展到简单的 Python 函数之外，与微服务、外部 API 或用其他语言编写的工具集成。

```python
from agenticle import MCP

# 连接到一个 MCP 服务器 (可以是一个本地脚本或一个远程 URL)
# 使用本地 Python 脚本的示例:
# mcp_server_endpoint = "python -m your_mcp_server_module"
# 使用远程服务器的示例:
# mcp_server_endpoint = "http://localhost:8000/mcp"

mcp_client = MCP(mcp_server_endpoint)

# MCP 客户端会自动从服务器列出工具
# 并将它们转换为 Agenticle 的 Tool 对象。
mcp_tools = mcp_client.list_tools()

# 现在，您可以将这些工具添加给任何智能体
remote_tool_agent = Agent(
    name="远程工具使用者",
    description="一个可以使用来自外部服务器工具的智能体。",
    tools=mcp_tools,
    # ... 其他智能体配置
)

# 该智能体现在可以像调用本地 Python 函数一样
# 调用 'get_database_records' 或 'process_image' 等工具。
remote_tool_agent.run("从数据库中获取最近 5 条用户记录。")
```

这个强大的特性使得 Agenticle 生态系统具有高度的可扩展性和互操作性。

## 关键概念

### Agent

`Agent` 是系统中的基本行动者。它通过以下参数进行初始化：
- `name`: 唯一的标识符。
- `description`: 高层次的任务目标。
- `input_parameters`: 其主要任务输入的模式（schema）。
- `tools`: 它可以使用的 `Tool` 对象列表。
- `endpoint` & `model_id`: 它应使用的大语言模型的配置。

### Group

`Group` 协调一个 `Agent` 实例列表。关键参数：
- `agents`: 群组中的智能体列表。
- `manager_agent_name`: 作为任务入口点的智能体的名称。
- `shared_tools`: 群组中所有智能体除了自己的工具外，都可以访问的 `Tool` 对象列表。
- `mode`:
    - `'broadcast'` (默认): 群组中的每个智能体都可以调用其他任何智能体。
    - `'manager_delegation'`: 只有管理者智能体可以调用其他智能体。专员智能体只能使用自己的工具和共享工具。
    - `'round_robin'`: 智能体按照提供的顺序依次执行。一个智能体的输出成为下一个智能体的输入，形成一个处理流水线。
- `workspace`: 一个可选的 `Workspace` 实例或文件路径，用于为群组中的所有智能体创建一个共享目录。

### 工作空间与状态管理

Agenticle 提供了强大的功能来管理状态和共享资源，这对于复杂的、长时间运行的任务至关重要。

#### 共享工作空间

您可以创建一个带有 `Workspace` 的 `Group`，这是一个沙盒化的目录，该群组中的所有智能体都可以在其中读写文件。这使得通过共享文件系统进行协作成为可能。

```python
from agenticle import Group, Workspace

# 在特定目录中创建一个工作空间，或留空以使用临时目录
my_workspace = Workspace(path="./my_shared_work_dir")

# 将工作空间提供给群组
my_group = Group(
    name="文件工作组",
    agents=[reader_agent, writer_agent],
    workspace=my_workspace
)
# 现在，reader_agent 和 writer_agent 都可以使用像
# read_file('data.txt') 和 write_file('result.txt') 这样的工具在工作空间内操作。
```

#### 保存与加载状态

对于可能被中断或需要稍后恢复的任务，您可以将 `Group` 的整个状态（包括每个智能体的对话历史）保存到一个文件，并在之后加载回来。

```python
# 假设 'travel_agency' 是一个正在运行的 Group
# ... 发生了一些交互 ...

# 保存当前状态
travel_agency.save_state("travel_agency_session.json")

# 稍后，您可以将群组恢复到之前的状态
# 首先，使用相同的配置创建群组
restored_agency = Group(...) 
# 然后，加载状态
restored_agency.load_state("travel_agency_session.json")

# 群组现在可以从它离开的地方继续执行任务。
```

## 理解事件流

当您使用 `stream=True` 运行智能体或群组时，框架会返回一个 `Event` 对象的迭代器。每个事件都实时地展示了智能体执行周期的内部情况。这对于构建用户界面、记录日志或调试非常有用。

每个 `Event` 都有一个 `source` (来源，例如 `Agent:Weather_Specialist`)、一个 `type` (类型) 和一个 `payload` (数据负载)。以下是您会遇到的关键事件类型：

-   **`start`**: 当智能体任务开始时触发一次。
    -   *Payload*: 传递给智能体的初始输入参数。
-   **`resume`**: 当 `Group` 或 `Agent` 从加载的状态继续执行时，会触发此事件以代替 `start`。
    -   *Payload*: 关于恢复的上下文信息，例如 `history_length`。
-   **`step`**: 标志着一个新的“思考-行动”循环的开始。
    -   *Payload*: 包含当前步骤编号 `current_step`。
-   **`reasoning_stream`**: 智能体在决定下一步做什么时的思考过程的连续流。
    -   *Payload*: 来自大语言模型推理过程的一个 `content` (内容) 片段。
-   **`content_stream`**: 如果大语言模型决定不调用工具而是直接回答，则此为最终答案内容的流。
    -   *Payload*: 最终答案的一个 `content` (内容) 片段。
-   **`decision`**: 当智能体做出调用工具或另一个智能体的明确决定时触发。
    -   *Payload*: 包含调用的 `tool_name` (工具名称) 和 `tool_args` (工具参数)。
-   **`tool_result`**: 在工具执行完毕后触发。
    -   *Payload*: 包含 `tool_name` (工具名称) 和工具返回的 `output` (输出)。
-   **`end`**: 最后一个事件，表示任务已完成。
    -   *Payload*: 包含 `final_answer` (最终答案)，如果任务失败则包含 `error` (错误) 消息。
-   **`error`**: 当发生导致进程终止的严重错误时触发。
    -   *Payload*: 一条错误 `message` (消息)。

## 高级用法: 使用提示词定制智能体行为

Agenticle 使用基于 Jinja2 的强大提示词模板系统来定义智能体的核心行为和推理过程。默认的提示词位于 `agenticle/prompts/default_agent_prompt.md`，它指示智能体遵循一个“思考-行动”循环。

您可以通过创建自己的提示词模板并将其文件路径传递给 `Agent` 的构造函数来定制此行为。

### 默认提示词 (`default_agent_prompt.md`)

默认模板为智能体建立了一个“认知框架”，引导它：
1.  **观察 (OBSERVE)**: 回顾目标和当前状态。
2.  **思考 (THINK)**: 评估信息，规划下一步，并选择一个工具或专家智能体。
3.  **行动 (ACT)**: 将其思考过程外化并执行所选的行动。

这种结构化的方法确保了透明和合乎逻辑的决策过程。

### 使用自定义提示词模板

要覆盖默认行为，只需在创建智能体时提供您的自定义 `.md` 模板文件的路径：

```python
my_custom_prompt_path = "path/to/your/custom_prompt.md"

custom_agent = Agent(
    name="自定义智能体",
    # ... 其他参数
    prompt_template_path=my_custom_prompt_path
)
```

这使您可以完全重新定义智能体的操作指南、个性，甚至是其推理结构。

### 模板变量

在创建自定义提示词时，您可以使用以下 Jinja2 变量，这些变量会自动传递给模板：

-   `{{ agent_name }}`: 智能体的名称。
-   `{{ agent_description }}`: 智能体的高层任务描述。
-   `{{ target_language }}`: 智能体响应所需的目标输出语言（例如 'English', 'Simplified Chinese'）。
-   `{{ plain_tools }}`: 对智能体可用的标准 `Tool` 对象列表。这些是常规的 Python 函数。
-   `{{ agent_tools }}`: 实际上是其他智能体的工具列表。这允许您在提示词中以不同的方式显示它们，例如作为“专家智能体”。
-   `{{ tools }}`: 所有工具的完整列表（包括 `plain_tools` 和 `agent_tools`）。
-   **自定义上下文变量**: 从 `Group` 传递的任何额外上下文（例如 `collaboration_mode`, `mode_description`）都可以在模板中访问。这允许基于协作策略实现高度自适应的智能体行为。

您可以在模板中遍历这些工具列表，以动态显示智能体的能力，如下所示：

```jinja
--- 基础工具 ---
{% for tool in plain_tools %}
**- {{ tool.name }}({% for p in tool.parameters %}{{ p.name }}: {{ p.get('annotation', 'any')}}{% if not loop.last %}, {% endif %}{% endfor %})**
  *功能*: {{ tool.description | indent(4) }}
{% endfor %}
```
