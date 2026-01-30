from typing import List, Literal

from pydantic import BaseModel

from vibe_cli.models.messages import ToolResult  # Re-export for tools/base.py

__all__ = ["ToolParameter", "ToolDefinition", "ToolResult"]


class ToolParameter(BaseModel):
    name: str
    type: Literal["string", "integer", "boolean", "array", "object"]
    description: str
    required: bool = True
    enum: list[str] | None = None

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: List[ToolParameter]
    dangerous: bool = False

    def to_openai_schema(self) -> dict:
        props = {}
        required = []
        for p in self.parameters:
            props[p.name] = {"type": p.type, "description": p.description}
            if p.enum:
                props[p.name]["enum"] = p.enum
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }

    def to_anthropic_schema(self) -> dict:
        props = {}
        required = []
        for p in self.parameters:
            props[p.name] = {"type": p.type, "description": p.description}
            if p.enum:
                props[p.name]["enum"] = p.enum
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        }
