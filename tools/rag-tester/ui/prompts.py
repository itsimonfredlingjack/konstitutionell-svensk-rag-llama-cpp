"""
Prompts module for RAG-Eval Terminal.
Handles user interaction using prompt_toolkit.
"""

from typing import Optional

from prompt_toolkit.shortcuts import input_dialog, radiolist_dialog


class MainMenu:
    """Handles the main menu interaction."""

    async def show(self) -> str:
        """Show the main menu and return choice."""
        # Using a simple input for menu to start, or prompt_toolkit shortcuts
        # A radiolist is good for menus
        result = await radiolist_dialog(
            title="RAG-Eval Terminal",
            text="Choose an action:\n(Use Arrows to move, Space to select, Tab to go to OK, then Enter)",
            values=[
                ("1", "🎲 Random Question"),
                ("2", "📂 Select Category"),
                ("3", "✍️  Custom Question"),
                ("4", "📜 View History"),
                ("q", "🚪 Quit"),
            ],
        ).run_async()
        return result


class CategorySelector:
    """Handles category selection."""

    async def select(self, categories: list[str]) -> Optional[str]:
        """Show category selector."""
        values = [(c, c.upper()) for c in categories]
        result = await radiolist_dialog(
            title="Select Category",
            text="Choose a question category:\n(Use Arrows to move, Space to select, Tab to go to OK)",
            values=values,
        ).run_async()
        return result


class RatingInput:
    """Handles rating input."""

    async def get_rating(self) -> tuple[int, Optional[str]]:
        """Get rating (1-5) and comment."""
        # 1. Get Star Rating
        rating = None
        while rating is None:
            rating_str = await radiolist_dialog(
                title="Rate Answer",
                text="How good was the answer?",
                values=[
                    (5, "⭐⭐⭐⭐⭐ (Perfect)"),
                    (4, "⭐⭐⭐⭐ (Good)"),
                    (3, "⭐⭐⭐ (Okay)"),
                    (2, "⭐⭐ (Poor)"),
                    (1, "⭐ (Bad)"),
                ],
            ).run_async()

            if rating_str:
                rating = int(rating_str)
            else:
                # If cancelled, maybe default to skipping or ask again?
                # For now let's insist or return None to signal abort savings?
                # Better to just return None rating to skip saving
                return 0, None

        # 2. Get Comment
        comment = await input_dialog(
            title="Comment", text="Optional comment (Press Enter to skip):"
        ).run_async()

        return rating, comment

    async def get_custom_question(self) -> Optional[str]:
        """Get a custom question text."""
        return await input_dialog(title="Custom Question", text="Enter your question:").run_async()


class ActionMenu:
    """Handles post-query actions."""

    async def show(self) -> str:
        """Show action menu."""
        result = await radiolist_dialog(
            title="Action Menu",
            text="What would you like to do?\n(Use Arrows/Space/Tab/Enter)",
            values=[
                ("rate", "Rate Answer"),
                ("inspect", "Inspect Sources"),
                ("continue", "Continue (Skip Rating)"),
            ],
        ).run_async()
        return result
