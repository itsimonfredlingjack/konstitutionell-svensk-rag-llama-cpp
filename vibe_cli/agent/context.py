from vibe_cli.models.messages import Conversation, Message, Role


class ContextManager:
    def __init__(
        self,
        provider,  # For token counting
        max_tokens: int = 100000,
        compress_threshold: float = 0.7,
    ):
        self.provider = provider
        self.max_tokens = max_tokens
        self.compress_threshold = compress_threshold

    def should_compress(self, conversation: Conversation) -> bool:
        return conversation.total_tokens > (self.max_tokens * self.compress_threshold)

    async def compress(self, conversation: Conversation) -> Conversation:
        """Summarize old messages to reduce token count"""

        if len(conversation.messages) < 4:
            return conversation

        # Keep system prompt and last 6 messages
        system_msgs = [m for m in conversation.messages if m.role == Role.SYSTEM]
        recent = conversation.messages[-6:]
        old = [m for m in conversation.messages[len(system_msgs):-6]]

        if not old:
            return conversation

        # Summarize old messages
        summary_prompt = self._build_summary_prompt(old)

        summary_text = ""
        # We use a lower temperature for summarization
        async for chunk in self.provider.complete(
            messages=[Message(role=Role.USER, content=summary_prompt)],
            tools=None,
            temperature=0.1,
        ):
            if chunk.text:
                summary_text += chunk.text
            if chunk.done:
                break

        # Build new compressed conversation
        new_messages = [
            *system_msgs,
            Message(
                role=Role.SYSTEM,
                content=f"[CONVERSATION SUMMARY]\n{summary_text}\n[END SUMMARY]",
            ),
            *recent,
        ]

        # Re-calculate tokens for new conversation (simplified)
        total_tokens = sum(m.tokens or self.provider.count_tokens(str(m.content)) for m in new_messages)

        return Conversation(
            id=conversation.id,
            messages=new_messages,
            total_tokens=total_tokens,
            created_at=conversation.created_at,
        )

    def _build_summary_prompt(self, messages: list[Message]) -> str:
        formatted = []
        for m in messages:
            if m.role == Role.USER:
                formatted.append(f"User: {m.content}")
            elif m.role == Role.ASSISTANT:
                content = m.content if isinstance(m.content, str) else str(m.content)
                formatted.append(f"Assistant: {content}")
            elif m.role == Role.TOOL:
                for r in m.tool_results or []:
                    formatted.append(f"Tool ({r.tool_call_id}): {r.content[:500]}...")

        return f"""Summarize this part of the conversation concisely.
Focus on:
1. Decisions made.
2. File paths and functions changed.
3. Errors fixed.

Conversation to summarize:
{chr(10).join(formatted)}

Summary:"""
