import asyncio
import logging
import signal
import sys

from .di import DIContainer


async def BootstrapApplication():
    di = DIContainer()
    interface = None
    try:
        await di.wire()
        logging.info("Starting application bootstrap...")

        # run consumers
        interface = di.interface_container
        await interface.consumer_interface.run_all()

        # keep the application running
        stop_event = asyncio.Event()

        if sys.platform != "win32":  # type: ignore
            # Linux / Mac: dùng signal handler
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop_event.set)
            await stop_event.wait()
        else:
            # Windows: dùng try/except KeyboardInterrupt
            try:
                await asyncio.Event().wait()  # chạy vô hạn
            except KeyboardInterrupt:
                logging.info("KeyboardInterrupt received, stopping...")
    finally:
        if interface is not None:
            logging.info("Shutting down consumers...")
            await interface.consumer_interface.stop_all()
        await di.shutdown()
