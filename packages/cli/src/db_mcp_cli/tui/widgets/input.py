"""CommandInput widget with slash-command autocomplete popover."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

# Command definitions: (name, description)
COMMANDS = [
    ("/add-rule", "add a business rule"),
    ("/cancel", "cancel pending execution"),
    ("/clear", "clear the feed"),
    ("/confirm", "confirm pending execution"),
    ("/dismiss", "dismiss pending knowledge gap"),
    ("/help", "show help"),
    ("/quit", "exit"),
    ("/status", "show server status"),
    ("/use", "switch connection"),
]


class CommandPalette(OptionList):
    """Filtered command list that appears above the input."""

    DEFAULT_CSS = """
    CommandPalette {
        height: auto;
        max-height: 12;
        display: none;
        background: $surface;
        border: solid $accent;
        padding: 0;
        margin: 0;
    }
    CommandPalette.visible {
        display: block;
    }
    """

    def filter(self, prefix: str) -> None:
        """Filter commands by prefix and show/hide."""
        self.clear_options()
        matches = [
            (name, desc)
            for name, desc in COMMANDS
            if name.startswith(prefix)
        ]
        if not matches or not prefix.startswith("/"):
            self.remove_class("visible")
            return
        for name, desc in matches:
            self.add_option(Option(f"{name}  [dim]{desc}[/]", id=name))
        self.add_class("visible")
        if self.option_count > 0:
            self.highlighted = 0


class CommandInput(Vertical):
    """Input bar with slash-command autocomplete popover."""

    DEFAULT_CSS = """
    CommandInput {
        dock: bottom;
        height: auto;
        max-height: 16;
    }
    CommandInput > Input {
        height: 1;
        border: none;
        background: $surface;
        padding: 0 1;
    }
    CommandInput > Input:focus {
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield CommandPalette()
        yield Input(placeholder="> ")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Changed)
    def _on_input_changed(self, event: Input.Changed) -> None:
        """Filter the palette as the user types."""
        value = event.value
        palette = self.query_one(CommandPalette)
        if value.startswith("/"):
            # Filter by the slash prefix (before any space)
            prefix = value.split(" ")[0]
            palette.filter(prefix)
        else:
            palette.remove_class("visible")

    @on(Input.Submitted)
    async def _on_input_submitted(self, event: Input.Submitted) -> None:
        """Dispatch the entered command."""
        raw = event.value.strip()
        if not raw:
            return
        inp = self.query_one(Input)
        inp.clear()
        self.query_one(CommandPalette).remove_class("visible")
        await self.app.dispatch_command(raw)

    @on(OptionList.OptionSelected)
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Insert the selected command into the input."""
        if event.option.id:
            inp = self.query_one(Input)
            # Commands that take args get a trailing space
            needs_arg = event.option.id in ("/add-rule", "/use")
            inp.value = event.option.id + (" " if needs_arg else "")
            inp.cursor_position = len(inp.value)
            inp.focus()
            self.query_one(CommandPalette).remove_class("visible")

    def on_key(self, event) -> None:
        """Route arrow keys to palette when visible."""
        palette = self.query_one(CommandPalette)
        if not palette.has_class("visible"):
            return
        if event.key in ("up", "down"):
            palette.focus()
            event.prevent_default()
        elif event.key == "escape":
            palette.remove_class("visible")
            self.query_one(Input).focus()
            event.prevent_default()
