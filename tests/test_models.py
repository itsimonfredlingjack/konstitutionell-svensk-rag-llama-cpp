from vibe_cli.models.messages import Message, Role, ToolCall
from vibe_cli.models.tools import ToolDefinition, ToolParameter


def test_message_serialization():
    msg = Message(
        role=Role.USER,
        content="Hello",
        tool_calls=[ToolCall(id="1", name="test", arguments={"a": 1})]
    )

    json_str = msg.model_dump_json()
    loaded = Message.model_validate_json(json_str)

    assert loaded.role == Role.USER
    assert loaded.content == "Hello"
    assert loaded.tool_calls[0].name == "test"
    assert loaded.tool_calls[0].arguments["a"] == 1

def test_tool_definition_schema():
    tool = ToolDefinition(
        name="read_file",
        description="Read a file",
        parameters=[
            ToolParameter(name="path", type="string", description="Path to file")
        ]
    )

    openai_schema = tool.to_openai_schema()
    assert openai_schema["function"]["name"] == "read_file"
    assert "path" in openai_schema["function"]["parameters"]["properties"]

    anthropic_schema = tool.to_anthropic_schema()
    assert anthropic_schema["name"] == "read_file"
    assert "path" in anthropic_schema["input_schema"]["properties"]
