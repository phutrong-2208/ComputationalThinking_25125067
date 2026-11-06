"""Verify Uvicorn over localhost and always stop the temporary server afterwards."""

import os
import socket
import subprocess
import sys
import time

import httpx

from exam_baseline.samples import sample_request


def main():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith("EXAM_")}
    env.update(EXAM_PROVIDER="mock", EXAM_MODEL="mock-fixture-v1")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "exam_baseline.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read().decode(errors="replace"))
                try:
                    health = client.get("/health", timeout=0.5)
                    health.raise_for_status()
                    break
                except httpx.TransportError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Uvicorn did not start within 15 seconds") from None
                    time.sleep(0.1)
            payload = sample_request().model_dump(mode="json")
            response = client.post("/v1/exams/generate", json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            assert result["status"] == "success", result
            assert result["validation"]["constraint_satisfaction_rate"] == 1
            print(
                f"Local HTTP smoke passed: {len(result['exam']['questions'])} questions, "
                f"{len(result['validation']['checks'])} checks, 100% satisfaction."
            )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()


if __name__ == "__main__":
    main()
