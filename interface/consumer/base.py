from typing import Protocol

class Runnable(Protocol):
    async def run(self) -> None:
        pass

    async def stop(self) -> None:
        pass
