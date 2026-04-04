"""CommandInput widget — text input for TUI commands."""

from __future__ import annotations

from textual.widgets import Input


class CommandInput(Input):
    """Command input bar docked above the status bar."""

    DEFAULT_CSS = """
    CommandInput {
        dock: bottom;
        height: 3;
        border-top: solid $accent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(placeholder="> ", **kwargs)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dispatch the entered command."""
        raw = event.value.strip()
        if not raw:
            return
        self.clear()
        await self.app.dispatch_command(raw)
