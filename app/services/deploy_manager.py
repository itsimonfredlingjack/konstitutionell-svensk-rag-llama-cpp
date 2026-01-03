"""
Deploy Manager - Git operations and service management
Handles deployment tasks for the mobile admin interface
"""

import asyncio
from typing import AsyncGenerator, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Project paths
PROJECT_ROOT = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/02_SIMONS-AI-BACKEND")

# Allowed services for restart
ALLOWED_SERVICES = ["simons-ai-backend", "simons-ai-frontend", "ollama"]

# Timeouts
GIT_TIMEOUT = 60
RESTART_TIMEOUT = 30


@dataclass
class DeployResult:
    """Result from a deploy operation"""
    success: bool
    operation: str
    output: str
    error: Optional[str] = None
    duration_ms: int = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "operation": self.operation,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class DeployProgress:
    """Progress update during deployment"""
    step: str
    status: str  # "pending", "running", "complete", "failed"
    message: str
    output: Optional[str] = None


class DeployManager:
    """
    Manages deployment operations:
    - Git pull
    - Service restart
    - Full deploy (pull + restart)
    """

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.project_root = project_root

    async def git_pull(self) -> DeployResult:
        """
        Pull latest changes from git.

        Uses --ff-only to prevent merge conflicts.
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Running git pull in {self.project_root}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(self.project_root), "pull", "--ff-only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=GIT_TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return DeployResult(
                    success=False,
                    operation="git_pull",
                    output="",
                    error=f"Git pull timed out after {GIT_TIMEOUT}s",
                    duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                    timestamp=timestamp,
                )

            duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                logger.info(f"Git pull successful: {stdout_str}")
                return DeployResult(
                    success=True,
                    operation="git_pull",
                    output=stdout_str or "Already up to date.",
                    duration_ms=duration_ms,
                    timestamp=timestamp,
                )
            else:
                logger.error(f"Git pull failed: {stderr_str}")
                return DeployResult(
                    success=False,
                    operation="git_pull",
                    output=stdout_str,
                    error=stderr_str or "Git pull failed",
                    duration_ms=duration_ms,
                    timestamp=timestamp,
                )

        except Exception as e:
            logger.error(f"Git pull error: {e}")
            return DeployResult(
                success=False,
                operation="git_pull",
                output="",
                error=str(e),
                duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                timestamp=timestamp,
            )

    async def git_status(self) -> DeployResult:
        """Get current git status"""
        timestamp = datetime.utcnow().isoformat() + "Z"
        start_time = asyncio.get_event_loop().time()

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(self.project_root), "status", "--short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=10
            )

            duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

            return DeployResult(
                success=proc.returncode == 0,
                operation="git_status",
                output=stdout.decode("utf-8", errors="replace").strip() or "Clean",
                error=stderr.decode("utf-8", errors="replace").strip() if proc.returncode != 0 else None,
                duration_ms=duration_ms,
                timestamp=timestamp,
            )

        except Exception as e:
            return DeployResult(
                success=False,
                operation="git_status",
                output="",
                error=str(e),
                timestamp=timestamp,
            )

    async def restart_service(self, service: str) -> DeployResult:
        """
        Restart a systemd service.

        Args:
            service: Service name (must be in ALLOWED_SERVICES)
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        start_time = asyncio.get_event_loop().time()

        # Validate service name
        if service not in ALLOWED_SERVICES:
            return DeployResult(
                success=False,
                operation=f"restart_{service}",
                output="",
                error=f"Service not allowed: {service}. Allowed: {ALLOWED_SERVICES}",
                timestamp=timestamp,
            )

        logger.info(f"Restarting service: {service}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "systemctl", "restart", service,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=RESTART_TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return DeployResult(
                    success=False,
                    operation=f"restart_{service}",
                    output="",
                    error=f"Service restart timed out after {RESTART_TIMEOUT}s",
                    duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                    timestamp=timestamp,
                )

            duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

            if proc.returncode == 0:
                logger.info(f"Service {service} restarted successfully")
                return DeployResult(
                    success=True,
                    operation=f"restart_{service}",
                    output=f"Service {service} restarted successfully",
                    duration_ms=duration_ms,
                    timestamp=timestamp,
                )
            else:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error(f"Failed to restart {service}: {error_msg}")
                return DeployResult(
                    success=False,
                    operation=f"restart_{service}",
                    output="",
                    error=error_msg or "Failed to restart service",
                    duration_ms=duration_ms,
                    timestamp=timestamp,
                )

        except Exception as e:
            logger.error(f"Service restart error: {e}")
            return DeployResult(
                success=False,
                operation=f"restart_{service}",
                output="",
                error=str(e),
                timestamp=timestamp,
            )

    async def get_service_status(self, service: str) -> DeployResult:
        """Get status of a systemd service"""
        timestamp = datetime.utcnow().isoformat() + "Z"

        if service not in ALLOWED_SERVICES:
            return DeployResult(
                success=False,
                operation=f"status_{service}",
                output="",
                error=f"Service not allowed: {service}",
                timestamp=timestamp,
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "is-active", service,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=5
            )

            status = stdout.decode("utf-8", errors="replace").strip()

            return DeployResult(
                success=status == "active",
                operation=f"status_{service}",
                output=status,
                error=None if status == "active" else f"Service is {status}",
                timestamp=timestamp,
            )

        except Exception as e:
            return DeployResult(
                success=False,
                operation=f"status_{service}",
                output="",
                error=str(e),
                timestamp=timestamp,
            )

    async def full_deploy(self) -> AsyncGenerator[DeployProgress, None]:
        """
        Full deployment: git pull + restart backend + restart frontend.

        Yields progress updates for each step.
        """
        steps = [
            ("git_pull", "Hämtar senaste kod..."),
            ("restart_backend", "Startar om backend..."),
            ("restart_frontend", "Startar om frontend..."),
        ]

        for step_id, step_msg in steps:
            yield DeployProgress(
                step=step_id,
                status="running",
                message=step_msg,
            )

            if step_id == "git_pull":
                result = await self.git_pull()
            elif step_id == "restart_backend":
                result = await self.restart_service("simons-ai-backend")
            elif step_id == "restart_frontend":
                result = await self.restart_service("simons-ai-frontend")

            if result.success:
                yield DeployProgress(
                    step=step_id,
                    status="complete",
                    message=f"{step_msg} Klart!",
                    output=result.output,
                )
            else:
                yield DeployProgress(
                    step=step_id,
                    status="failed",
                    message=f"{step_msg} Misslyckades: {result.error}",
                    output=result.output,
                )
                # Stop on failure
                return

        yield DeployProgress(
            step="complete",
            status="complete",
            message="Deploy klar!",
        )


# Global manager instance
deploy_manager = DeployManager()


async def get_deploy_manager() -> DeployManager:
    """Dependency injection helper"""
    return deploy_manager
