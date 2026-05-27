import os
import tempfile
import time
from pathlib import Path
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound, NotFound
from docker.models.containers import Container


SANDBOX_IMAGE = "python:3.11-slim"
CONTAINER_INPUT_DIR = "/sandbox/input"
CONTAINER_OUTPUT_DIR = "/sandbox/output"
CONTAINER_SCRIPT_PATH = f"{CONTAINER_INPUT_DIR}/script.py"


def _decode_logs(raw_logs: bytes | str) -> str:
    if isinstance(raw_logs, str):
        return raw_logs
    return raw_logs.decode("utf-8", errors="replace")


def _collect_logs(container: Container) -> tuple[str, str]:
    stdout = _decode_logs(container.logs(stdout=True, stderr=False))
    stderr = _decode_logs(container.logs(stdout=False, stderr=True))
    return stdout, stderr


def _wait_for_container(container: Container, timeout: int) -> int:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        container.reload()
        if container.status == "exited":
            state: dict[str, Any] = container.attrs.get("State", {})
            exit_code = state.get("ExitCode")
            return int(exit_code) if exit_code is not None else -1
        time.sleep(0.1)

    raise TimeoutError(f"Sandbox execution timed out after {timeout} seconds.")


def execute_in_sandbox(script_content: str, timeout: int = 10) -> dict:
    """Run Python code inside a short-lived, restricted Docker container.

    Security controls:
    - python:3.11-slim runtime image
    - network disabled
    - non-root user
    - read-only root filesystem
    - read-only script mount plus writable output mount
    - 128 MB memory limit
    """

    if timeout < 1:
        raise ValueError("timeout must be greater than or equal to 1.")

    container: Container | None = None

    with tempfile.TemporaryDirectory(prefix="paos_sandbox_") as temp_dir:
        base_dir = Path(temp_dir)
        input_dir = base_dir / "input"
        output_dir = base_dir / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        script_path = input_dir / "script.py"
        script_path.write_text(script_content, encoding="utf-8")

        # The container runs as nobody, so the bind-mounted paths must be readable.
        os.chmod(input_dir, 0o755)
        os.chmod(output_dir, 0o777)
        os.chmod(script_path, 0o444)

        try:
            client = docker.from_env()
            try:
                client.images.get(SANDBOX_IMAGE)
            except ImageNotFound:
                client.images.pull(SANDBOX_IMAGE)

            container = client.containers.create(
                image=SANDBOX_IMAGE,
                command=["python", CONTAINER_SCRIPT_PATH],
                detach=True,
                network_disabled=True,
                mem_limit="128m",
                user="65534:65534",
                read_only=True,
                working_dir=CONTAINER_OUTPUT_DIR,
                volumes={
                    str(input_dir): {"bind": CONTAINER_INPUT_DIR, "mode": "ro"},
                    str(output_dir): {"bind": CONTAINER_OUTPUT_DIR, "mode": "rw"},
                },
            )
            container.start()

            try:
                exit_code = _wait_for_container(container, timeout)
                stdout, stderr = _collect_logs(container)
            except TimeoutError as exc:
                container.kill()
                stdout, stderr = _collect_logs(container)
                exit_code = 124
                stderr = f"{stderr}\n{exc}".strip()

            return {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
            }
        except DockerException as exc:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Docker sandbox error: {exc}",
            }
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except NotFound:
                    pass
