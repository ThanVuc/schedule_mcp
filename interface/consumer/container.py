import asyncio
from interface.consumer.base import Runnable
import logging

class ConsumerContainer:
    def __init__(self):
        self._runnables: list[Runnable] = []
        self._tasks: list[asyncio.Task] = []

    def add_consumer(self, consumer: Runnable) -> None:
        self._runnables.append(consumer)

    def get_consumers(self):
        return self._runnables

    async def run_all(self):
        """Start all consumers concurrently."""
        for runnable in self._runnables:
            task = asyncio.create_task(runnable.run())
            self._tasks.append(task)
        logging.info("All consumers are running.")

    async def stop_all(self):
        """Gracefully stop all consumers."""
        for runnable in self._runnables:
            await runnable.stop()

        for task in self._tasks:
            task.cancel()
        
        logging.info("All consumers have been stopped.")

        
