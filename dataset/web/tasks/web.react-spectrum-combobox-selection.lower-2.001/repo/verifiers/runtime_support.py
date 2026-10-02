"""Wait for the test-owned service before checking application behavior."""
import socket
import time


def wait_for_service(process, port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("EVALUATION_SETUP_ERROR: test data service exited before readiness")
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("EVALUATION_SETUP_ERROR: test data service did not start")
