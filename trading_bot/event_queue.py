import queue
from typing import Any, Optional

class EventQueue:
    """
    Thread-safe, in-memory event queue for inter-component communication.

    Args:
        maxsize (int): Maximum size of the queue. 0 means infinite.
    """
    def __init__(self, maxsize: int = 0) -> None:
        """
        Initialize the event queue.

        Args:
            maxsize (int): Maximum size of the queue. 0 means infinite.
        """
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)

    def put(self, event: Any) -> None:
        """
        Enqueue an event.

        Args:
            event (Any): The event object to enqueue.
        """
        self._queue.put(event)

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        """
        Dequeue an event.

        Args:
            block (bool): Whether to block if the queue is empty.
            timeout (Optional[float]): Timeout for blocking.

        Returns:
            Any: The next event object.
        """
        return self._queue.get(block=block, timeout=timeout)

    def empty(self) -> bool:
        """
        Check if the queue is empty.

        Returns:
            bool: True if empty, False otherwise.
        """
        return self._queue.empty()

    def qsize(self) -> int:
        """
        Return the size of the queue.

        Returns:
            int: Number of events in the queue.
        """
        return self._queue.qsize() 