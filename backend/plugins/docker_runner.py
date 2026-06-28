import asyncio
import logging
import time

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

logger = logging.getLogger("DockerRunner")

class DockerSandbox:
    def __init__(self):
        self.available = DOCKER_AVAILABLE
        self.client = None
        if self.available:
            try:
                self.client = docker.from_env()
                # Test connection
                self.client.ping()
            except Exception as e:
                logger.error(f"Docker engine not running or reachable: {e}")
                self.available = False

    async def execute_code(self, code: str, language: str = "python") -> str:
        if not self.available or not self.client:
            return "Docker sandbox unavailable. Falling back to local/AST runner."
            
        image_map = {
            "python": "python:3.11-alpine",
            "js": "node:18-alpine",
            "sh": "alpine:latest"
        }
        
        image = image_map.get(language, "python:3.11-alpine")
        
        try:
            # Clean up the code
            code = code.replace("'", "'\\''")
            
            if language == "python":
                cmd = f"python -c '{code}'"
            elif language == "js":
                cmd = f"node -e '{code}'"
            else:
                cmd = f"sh -c '{code}'"

            # Run securely in a throwaway container with strict limits
            try:
                result = await asyncio.to_thread(
                    self.client.containers.run,
                    image,
                    cmd,
                    detach=False, # Wait for it to finish
                    mem_limit="128m",
                    cpu_quota=50000,
                    network_disabled=True,
                    remove=True # Keep it clean
                )
                return result.decode("utf-8")
            except docker.errors.ContainerError as e:
                # Execution failed
                return f"Error: Container exited with code {e.exit_status}.\n\nTraceback / Logs:\n{e.stderr.decode('utf-8')}"
            except Exception as e:
                return f"Error: Sandbox execution failed: {e}"

sandbox_runner = DockerSandbox()
