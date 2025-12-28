from typing import Protocol

class Runnable(Protocol):
    def run(self) -> None:
        pass

    def stop(self) -> None:
        pass
