from pydantic import BaseModel


class StreamChunk(BaseModel):
    text: str | None = None
    done: bool = False
    usage: dict | None = None
    metadata: dict | None = None
