import queue
from typing import Dict, Any, Optional

class Event:
    """Defines a standard event structure."""
    def __init__(self, source: str, type: str, payload: Optional[Dict[str, Any]] = None):
        """Initializes an Event.

        Args:
            source (str): The origin of the event, e.g., "Agent:Travel_Planner".
            type (str): The type of the event, e.g., "decision", "tool_call", "tool_result".
            payload (Optional[Dict[str, Any]]): The specific data of the event.
        """
        self.source = source
        self.type = type
        self.payload = payload or {}

    def __repr__(self):
        """Provides a string representation of the Event instance."""
        return f"Event(source={self.source}, type={self.type}, payload={self.payload})"

class EventBroker:
    """A simple event broker that uses a queue to decouple event producers and consumers."""
    def __init__(self):
        """Initializes the EventBroker."""
        self.queue = queue.Queue()

    def emit(self, source: str, type: str, payload: Optional[Dict[str, Any]] = None):
        """Creates an event and puts it into the queue.

        Args:
            source (str): The origin of the event.
            type (str): The type of the event.
            payload (Optional[Dict[str, Any]]): The specific data of the event.
        """
        event = Event(source, type, payload)
        self.queue.put(event)

def pass_event(iterator) -> Event:
    event: Event = None
    for event in iterator: pass
    return event