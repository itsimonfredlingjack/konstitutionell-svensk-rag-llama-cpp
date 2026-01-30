import asyncio
import json
from typing import Any

from rag_cli.models.tools import ToolParameter
from rag_cli.tools.base import Tool, ToolDefinition, ToolResult


class AWSResourceLister(Tool):
    def __init__(self) -> None:
        self._resource_map = {
            "s3_buckets": ["s3api", "list-buckets"],
            "ec2_instances": ["ec2", "describe-instances"],
            "rds_instances": ["rds", "describe-db-instances"],
            "ecs_clusters": ["ecs", "list-clusters"],
        }

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="aws_list_resources",
            description="List AWS resources via AWS CLI and return JSON.",
            parameters=[
                ToolParameter(
                    name="resource",
                    type="string",
                    description="Resource type (s3_buckets, ec2_instances, rds_instances, ecs_clusters)",
                    enum=list(self._resource_map.keys()),
                ),
                ToolParameter(
                    name="region",
                    type="string",
                    description="AWS region (optional)",
                    required=False,
                ),
            ],
            dangerous=True,
        )

    async def execute(self, resource: str, region: str | None = None) -> ToolResult:
        if resource not in self._resource_map:
            return ToolResult(tool_call_id="", content=f"Unknown resource: {resource}", is_error=True)

        args = ["aws", *self._resource_map[resource], "--output", "json"]
        if region:
            args.extend(["--region", region])

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ToolResult(tool_call_id="", content="AWS CLI not found on PATH", is_error=True)

        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip() or "AWS CLI failed"
            return ToolResult(tool_call_id="", content=err, is_error=True)

        try:
            data: Any = json.loads(stdout.decode())
        except json.JSONDecodeError:
            data = {"raw": stdout.decode()}

        return ToolResult(tool_call_id="", content=json.dumps(data, indent=2), is_error=False)


class K8sLogFetcher(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="k8s_fetch_logs",
            description="Fetch Kubernetes pod logs and return structured JSON.",
            parameters=[
                ToolParameter(name="pod", type="string", description="Pod name"),
                ToolParameter(name="namespace", type="string", description="Namespace", required=False),
                ToolParameter(name="container", type="string", description="Container name", required=False),
                ToolParameter(name="tail_lines", type="integer", description="Tail lines", required=False),
            ],
            dangerous=True,
        )

    async def execute(
        self,
        pod: str,
        namespace: str | None = None,
        container: str | None = None,
        tail_lines: int | None = None,
    ) -> ToolResult:
        args = ["kubectl", "logs", pod]
        if namespace:
            args.extend(["--namespace", namespace])
        if container:
            args.extend(["-c", container])
        if tail_lines:
            args.extend(["--tail", str(tail_lines)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ToolResult(tool_call_id="", content="kubectl not found on PATH", is_error=True)

        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip() or "kubectl logs failed"
            return ToolResult(tool_call_id="", content=err, is_error=True)

        logs = stdout.decode().splitlines()
        payload = {
            "pod": pod,
            "namespace": namespace or "default",
            "container": container,
            "lines": len(logs),
            "logs": logs,
        }
        return ToolResult(tool_call_id="", content=json.dumps(payload, indent=2), is_error=False)
