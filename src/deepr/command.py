"""Minimal command framework built on prompt_toolkit and Rich."""

import inspect
import pathlib
import sys
import typing as T

import prompt_toolkit as ptk
import prompt_toolkit.completion as ptkc
import prompt_toolkit.document as ptkd
import prompt_toolkit.history as ptkh
import rich.console as rc


# ---------------------------------------------------------------------------
# Command decorator
# ---------------------------------------------------------------------------

_COMMAND_ATTR = "_command_info"


class CommandInfo(T.NamedTuple):
    """Metadata stored on a decorated command method."""

    name: str
    description: str


def command(
    name: str | None = None,
    description: str | None = None,
) -> T.Callable[[T.Callable[..., None]], T.Callable[..., None]]:
    """Register a method as a slash command.

    Both *name* and *description* are optional.  When omitted the name is
    derived from the function name by stripping a leading ``cmd_`` prefix,
    and the description is taken from the first line of the docstring.

    Usage::

        class MyApp(CommandApp):
            @command()
            def cmd_greet(self, args: str) -> None:
                \"\"\"Say hello.\"\"\"
                self.poutput(f"Hello, {args or 'world'}!")
    """

    def decorator(fn: T.Callable[..., None]) -> T.Callable[..., None]:
        cmd_name = name if name is not None else _name_from_function(fn)
        cmd_desc = (
            description if description is not None else _description_from_docstring(fn)
        )
        setattr(fn, _COMMAND_ATTR, CommandInfo(cmd_name, cmd_desc))
        return fn

    return decorator


def _name_from_function(fn: T.Callable[..., T.Any]) -> str:
    """Derive a command name from a function name by stripping a ``cmd_`` prefix."""
    func_name = inspect.unwrap(fn).__qualname__.rsplit(".", 1)[-1]
    if func_name.startswith("cmd_"):
        return func_name[4:]
    return func_name


def _description_from_docstring(fn: T.Callable[..., T.Any]) -> str:
    """Extract the first line of a function's docstring, or return ``""``."""
    doc = inspect.getdoc(fn)
    if not doc:
        return ""
    return doc.split("\n", 1)[0].strip()


# ---------------------------------------------------------------------------
# Completer
# ---------------------------------------------------------------------------


class _CommandCompleter(ptkc.Completer):
    """Show command completions as the user types."""

    def __init__(self, commands: dict[str, tuple[T.Any, str]]) -> None:
        self._commands = commands

    def get_completions(
        self,
        document: ptkd.Document,
        complete_event: ptkc.CompleteEvent,
    ) -> T.Iterator[ptkc.Completion]:
        text = document.text_before_cursor
        # Only complete when the line starts with '/' and cursor is in that first word.
        if not text.startswith("/") or " " in text:
            return
        for name in ["help", *sorted(self._commands)]:
            full = f"/{name}"
            if full.startswith(text):
                yield ptkc.Completion(
                    full,
                    start_position=-len(text),
                    display_meta=self._commands[name][1]
                    if name in self._commands
                    else "Show available commands.",
                )


# ---------------------------------------------------------------------------
# CommandApp base class
# ---------------------------------------------------------------------------


class CommandApp:
    """Interactive command loop where ``/``-prefixed input dispatches to commands
    and everything else is forwarded to :meth:`default`.

    Subclass this and decorate methods with :func:`command` to add commands.
    Override :meth:`default` to handle non-command input.
    """

    def __init__(
        self,
        *,
        prompt: str = "> ",
        history_file: str | pathlib.Path | None = None,
        intro: str | None = None,
        prog: str | None = None,
        description: str | None = None,
    ) -> None:
        self._prompt = prompt
        self._history_file = (
            pathlib.Path(history_file).expanduser() if history_file else None
        )
        self._intro = intro
        self._prog = prog
        self._description = description
        self._console = rc.Console()
        self._err_console = rc.Console(stderr=True)

        # Collect commands by inspecting class dictionaries across the MRO.
        # This avoids triggering properties/descriptors with side effects that
        # a ``dir()`` + ``getattr(self, ...)`` walk would.
        self._commands: dict[str, tuple[T.Callable[[str], None], str]] = {}
        seen: set[str] = set()
        for cls in type(self).__mro__:
            for attr_name, attr in vars(cls).items():
                if attr_name in seen:
                    continue
                seen.add(attr_name)
                info: CommandInfo | None = getattr(attr, _COMMAND_ATTR, None)
                if info is not None:
                    bound = getattr(self, attr_name)
                    self._commands[info.name] = (bound, info.description)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Parse CLI arguments; dispatch non-interactively or enter the command loop."""
        import sys

        args = sys.argv[1:]

        if not args or args == []:
            self.cmdloop()
            return

        if args[0] in ("-h", "--help"):
            topic = " ".join(args[1:]).strip()
            if topic:
                self._builtin_help(topic)
            else:
                self._print_usage()
            return

        head = args[0].lstrip("/").lower()
        all_commands = {"help", *self._commands}

        if head in all_commands:
            rest = " ".join(args[1:])
            if head == "help":
                self._builtin_help(rest)
            else:
                self._commands[head][0](rest)
        else:
            self.default(" ".join(args))

    def _print_usage(self) -> None:
        """Print argparse-style usage and command list."""
        prog = self._prog or "app"
        all_commands = ["help", *sorted(self._commands)]
        choices = ",".join(all_commands)

        lines = [
            f"usage: {prog} [-h] {{{choices}}} ...",
            "",
        ]
        if self._description:
            lines += [self._description, ""]

        lines.append("commands:")
        descs = [("help", "Show available commands.")]
        descs += [(name, desc) for name, (_, desc) in sorted(self._commands.items())]
        col_width = max(len(n) for n, _ in descs) + 2
        for name, desc in descs:
            lines.append(f"  {name:<{col_width}}{desc}")

        lines += [
            "",
            "options:",
            "  -h, --help    show this help message and exit",
            "",
            "Any other arguments are passed as a research query.",
        ]

        for line in lines:
            self.poutput(line)

    def cmdloop(self) -> None:
        """Run the interactive command loop."""
        session = self._create_session()
        self.preloop()

        if self._intro is not None:
            self.poutput(self._intro)

        try:
            while True:
                try:
                    line = session.prompt(self._prompt)
                except EOFError:
                    self.poutput("")
                    break
                except KeyboardInterrupt:
                    continue
                self._dispatch(line)
        finally:
            self.postloop()

    def _create_session(self) -> ptk.PromptSession[str]:
        """Build a prompt_toolkit session with history and completion."""
        history: ptkh.History | None = None
        if self._history_file is not None:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            history = ptkh.FileHistory(str(self._history_file))
        return ptk.PromptSession(
            completer=_CommandCompleter(self._commands),
            complete_while_typing=True,
            history=history,
        )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, line: str) -> None:
        """Route *line* to a command handler or :meth:`default`."""
        stripped = line.strip()
        if not stripped:
            return

        if stripped.startswith("/"):
            parts = stripped[1:].split(None, 1)
            cmd_name = parts[0].lower() if parts else ""
            cmd_args = parts[1] if len(parts) > 1 else ""

            if cmd_name == "help":
                self._builtin_help(cmd_args)
                return

            handler_tuple = self._commands.get(cmd_name)
            if handler_tuple is None:
                self.perror(f"Unknown command: /{cmd_name}")
                return
            handler_tuple[0](cmd_args)
        else:
            self.default(stripped)

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    def default(self, text: str) -> None:
        """Handle input that is not a slash command.

        Override in subclasses to provide domain-specific behaviour.
        The base implementation does nothing.
        """

    def preloop(self) -> None:
        """Called once before the command loop starts. Override as needed."""

    def postloop(self) -> None:
        """Called once after the command loop ends. Override as needed."""

    # ------------------------------------------------------------------
    # Built-in /help
    # ------------------------------------------------------------------

    def _builtin_help(self, args: str) -> None:
        """Print a list of available slash commands."""
        if args:
            cmd_name = args.strip().lower().lstrip("/")
            handler_tuple = self._commands.get(cmd_name)
            if handler_tuple is None:
                self.perror(f"Unknown command: /{cmd_name}")
                return
            self.poutput(f"  /{cmd_name:<12s} {handler_tuple[1]}")
            return

        self.poutput("  /help         Show available commands.")
        for name, (_, desc) in sorted(self._commands.items()):
            self.poutput(f"  /{name:<12s} {desc}")

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def poutput(self, text: object = "") -> None:
        """Print *text* to stdout via Rich."""
        self._console.print(text, highlight=False)

    def perror(self, text: object = "") -> None:
        """Print *text* to stderr in red via Rich."""
        self._err_console.print(text, style="red", highlight=False)

    def notify(self, message: str) -> None:
        """Send a desktop notification via OSC 9 terminal escape.

        Most modern terminals (iTerm2, WezTerm, Ghostty, Windows Terminal,
        GNOME Terminal, VS Code) will display this as a system notification.
        Terminals that do not support OSC 9 silently ignore the sequence.
        """
        sys.stderr.write(f"\033]9;{message}\a")
        sys.stderr.flush()
