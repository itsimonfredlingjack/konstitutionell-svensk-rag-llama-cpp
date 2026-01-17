#!/usr/bin/env python3
"""
RAG-Eval Terminal - Main Entry Point
"""

import asyncio

from rich.console import Console

try:
    from tools.rag_tester.core import api_client, question_bank, rating_store
    from tools.rag_tester.ui.display import Dashboard, HistoryView, SourceInspector, StreamRenderer
    from tools.rag_tester.ui.prompts import ActionMenu, CategorySelector, MainMenu, RatingInput
except ImportError:
    # Fallback for running directly from the directory
    from core import api_client, question_bank, rating_store
    from ui.display import Dashboard, HistoryView, SourceInspector, StreamRenderer
    from ui.prompts import ActionMenu, CategorySelector, MainMenu, RatingInput


class RagTesterApp:
    def __init__(self):
        self.console = Console()
        self.dashboard = Dashboard(self.console)
        self.history_view = HistoryView(self.console)
        self.menu = MainMenu()
        self.cat_selector = CategorySelector()
        self.rater = RatingInput()
        self.action_menu = ActionMenu()
        self.inspector = SourceInspector(self.console)

        # Core
        self.q_bank = question_bank.get_bank()
        self.store = rating_store.get_store()

    async def run_test(self, question_data: dict):
        """Run a single test flow."""
        question_text = question_data["question"]
        qid = question_data.get("id", "manual")

        # 1. Setup Streaming UI
        expected = question_data.get("expected")
        renderer = StreamRenderer(self.console, question_text, expected=expected)
        renderer.start()

        full_answer = ""

        try:
            # 2. Query API
            async for event in api_client.query_rag(question_text):
                
                if event.type == "token":
                    renderer.update_token(event.data)
                    full_answer += event.data
                elif event.type == "sources":
                    renderer.set_sources(event.data)
                elif event.type == "done":
                    renderer.done()
                elif event.type == "error":
                    renderer.update_token(f"\n[ERROR] {event.data}")
                    renderer.done()
        except Exception as e:
            renderer.update_token(f"\n[EXCEPTION] {e!s}")
            renderer.done()
        finally:
            renderer.stop()

        # Explicit Barrier: Forces user to acknowledge end of stream
        # unexpected EOF or fast inputs are handled better by PromptSession
        from prompt_toolkit import PromptSession
        from prompt_toolkit.styles import Style
        
        # Use our theme for consistency
        barrier_style = Style.from_dict({
            'prompt': 'bold white',
        })
        
        try:
            session = PromptSession(style=barrier_style)
            await asyncio.to_thread(session.prompt, "[ Press Enter to Open Action Menu ]")
            # Clear lines? No, let's keep it simple.
        except (EOFError, KeyboardInterrupt):
             pass # just proceed to menu or let menu handle quit

        # 3. Action Logic (Rate or Inspect)
        while True:
            # Re-render the last frame to keep context
            renderer.persist()

            action = await self.action_menu.show()

            if action == "inspect":
                sources = renderer.get_sources()
                await self.inspector.show(sources)
                # After inspection, loop back to menu
                continue

            elif action == "rate":
                rating, comment = await self.rater.get_rating()

                if rating > 0:
                    self.store.save_rating(
                        question_id=qid,
                        question_text=question_text,
                        answer=full_answer,
                        rating=rating,
                        comment=comment,
                    )
                    self.console.print(f"\n[green]Rating saved! ({rating}/5)[/green]")
                else:
                    self.console.print("\n[yellow]Rating skipped (User cancelled).[/yellow]")
                break

            elif action == "continue" or action is None:
                self.console.print("\n[yellow]Skipping rating.[/yellow]")
                break

        await asyncio.sleep(1.0)

    async def main_loop(self):
        """Main event loop."""
        while True:
            # Show Dashboard Stats briefly or as part of menu?
            # User requested "Start with a Dashboard... Meny: ..."
            # Let's show dashboard then menu dialog.

            stats = self.store.get_stats()
            # Add trend data for sparkline
            stats["trend_data"] = self.store.get_trend_data(limit=10)  # 10 chars fits nicely
            self.dashboard.render(stats)

            # Show Menu
            choice = await self.menu.show()

            if not choice or choice == "q":
                self.console.print("Goodbye!")
                break

            if choice == "1":  # Random Question
                q = self.q_bank.get_random()
                if q:
                    await self.run_test(q.to_dict())
                else:
                    self.console.print("[red]No questions in bank![/red]")
                    await asyncio.sleep(2)

            elif choice == "2":  # Select Category
                cats = self.q_bank.list_categories()
                cat = await self.cat_selector.select(cats)
                if cat:
                    q = self.q_bank.get_random(category=cat)
                    if q:
                        await self.run_test(q.to_dict())
                    else:
                        self.console.print(f"[red]No questions in category {cat}![/red]")
                        await asyncio.sleep(2)

            elif choice == "3":  # Custom Question
                q_text = await self.rater.get_custom_question()
                if q_text:
                    await self.run_test({"question": q_text, "id": "manual"})

            elif choice == "4":  # View History
                # Show history for a specific question? Or all recent?
                # "Show past ratings for a specific question" was useful, but "View History" in menu usually implies global.
                # Let's show recent global history for now to match "Dashboard" feel.
                recent = [
                    {
                        "timestamp": r.timestamp,
                        "rating": r.rating,
                        "comment": f"[{r.question_text[:30]}...] {r.comment or ''}",
                    }
                    for r in self.store.get_recent(20)
                ]
                self.history_view.render(recent)
                input()  # wait for enter


async def main():
    app = RagTesterApp()
    await app.main_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
