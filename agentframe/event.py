import queue
from typing import Dict, Any, Optional

class Event:
    """定义一个标准的事件结构。"""
    def __init__(self, source: str, type: str, payload: Optional[Dict[str, Any]] = None):
        self.source = source  # 事件来源, e.g., "Agent:Travel_Planner"
        self.type = type      # 事件类型, e.g., "decision", "tool_call", "tool_result"
        self.payload = payload or {} # 事件的具体数据

    def __repr__(self):
        return f"Event(source={self.source}, type={self.type}, payload={self.payload})"

class EventBroker:
    """一个简单的事件代理，使用队列来解耦事件的生产者和消费者。"""
    def __init__(self):
        self.queue = queue.Queue()

    def emit(self, source: str, type: str, payload: Optional[Dict[str, Any]] = None):
        """创建一个事件并将其放入队列。"""
        event = Event(source, type, payload)
        self.queue.put(event)