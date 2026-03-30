"""Tests for the CommandApp command framework."""

import prompt_toolkit.document as ptkd
import prompt_toolkit.completion as ptkc

from deepr.command import CommandApp, _CommandCompleter, command


# ---------------------------------------------------------------------------
# Test fixture: a concrete CommandApp subclass that records calls
# ---------------------------------------------------------------------------


class RecordingApp(CommandApp):
    """CommandApp subclass that records command and default invocations."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls: list[tuple[str, str]] = []

    @command("greet", "Say hello.")
    def cmd_greet(self, args: str) -> None:
        self.calls.append(("greet", args))

    @command("save", "Save a file.")
    def cmd_save(self, args: str) -> None:
        self.calls.append(("save", args))

    def default(self, text: str) -> None:
        self.calls.append(("default", text))


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


class TestCommandRegistration:
    def test_decorated_commands_are_registered(self):
        app = RecordingApp()
        assert "greet" in app._commands
        assert "save" in app._commands

    def test_help_is_not_in_commands_dict(self):
        """``/help`` is a built-in handled separately from the commands dict."""
        app = RecordingApp()
        assert "help" not in app._commands

    def test_command_descriptions(self):
        app = RecordingApp()
        assert app._commands["greet"][1] == "Say hello."
        assert app._commands["save"][1] == "Save a file."


# ---------------------------------------------------------------------------
# Dispatch routing
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_slash_command_routes_to_handler(self):
        app = RecordingApp()
        app._dispatch("/greet world")
        assert app.calls == [("greet", "world")]

    def test_slash_command_no_args(self):
        app = RecordingApp()
        app._dispatch("/save")
        assert app.calls == [("save", "")]

    def test_bare_text_routes_to_default(self):
        app = RecordingApp()
        app._dispatch("help me with something")
        assert app.calls == [("default", "help me with something")]

    def test_empty_input_is_ignored(self):
        app = RecordingApp()
        app._dispatch("")
        assert app.calls == []

    def test_whitespace_only_is_ignored(self):
        app = RecordingApp()
        app._dispatch("   \t  ")
        assert app.calls == []

    def test_unknown_slash_command_prints_error(self, capsys):
        app = RecordingApp()
        app._dispatch("/unknown")
        captured = capsys.readouterr()
        assert "Unknown command: /unknown" in captured.err
        assert app.calls == []

    def test_slash_alone_prints_error(self, capsys):
        app = RecordingApp()
        app._dispatch("/")
        captured = capsys.readouterr()
        assert "Unknown command" in captured.err

    def test_command_name_is_case_insensitive(self):
        app = RecordingApp()
        app._dispatch("/GREET World")
        assert app.calls == [("greet", "World")]

    def test_leading_whitespace_is_stripped(self):
        app = RecordingApp()
        app._dispatch("  /greet hi")
        assert app.calls == [("greet", "hi")]

    def test_bare_text_is_stripped(self):
        app = RecordingApp()
        app._dispatch("  hello  ")
        assert app.calls == [("default", "hello")]


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestArguments:
    def test_multi_word_args(self):
        app = RecordingApp()
        app._dispatch("/save my report.pdf")
        assert app.calls == [("save", "my report.pdf")]

    def test_args_preserve_internal_whitespace(self):
        app = RecordingApp()
        app._dispatch("/greet hello   world")
        assert app.calls == [("greet", "hello   world")]


# ---------------------------------------------------------------------------
# Built-in /help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_lists_commands(self, capsys):
        app = RecordingApp()
        app._dispatch("/help")
        captured = capsys.readouterr()
        assert "/greet" in captured.out
        assert "/save" in captured.out
        assert "/help" in captured.out

    def test_help_specific_command(self, capsys):
        app = RecordingApp()
        app._dispatch("/help greet")
        captured = capsys.readouterr()
        assert "/greet" in captured.out
        assert "Say hello." in captured.out

    def test_help_unknown_command(self, capsys):
        app = RecordingApp()
        app._dispatch("/help nope")
        captured = capsys.readouterr()
        assert "Unknown command: /nope" in captured.err


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


class TestOutput:
    def test_poutput_writes_to_stdout(self, capsys):
        app = RecordingApp()
        app.poutput("hello")
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_perror_writes_to_stderr(self, capsys):
        app = RecordingApp()
        app.perror("bad thing")
        captured = capsys.readouterr()
        assert "bad thing" in captured.err

    def test_notify_writes_osc9_to_stderr(self, capsys):
        app = RecordingApp()
        app.notify("Research complete")
        captured = capsys.readouterr()
        assert captured.err == "\033]9;Research complete\a"

    def test_notify_does_not_write_to_stdout(self, capsys):
        app = RecordingApp()
        app.notify("hello")
        captured = capsys.readouterr()
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Non-interactive run()
# ---------------------------------------------------------------------------


class TestNonInteractiveRun:
    def test_run_dispatches_subcommand(self, monkeypatch):
        app = RecordingApp()
        monkeypatch.setattr(
            "sys.argv",
            ["test", "greet", "world"],
        )
        app.run()
        assert app.calls == [("greet", "world")]

    def test_run_dispatches_bare_text(self, monkeypatch):
        app = RecordingApp()
        monkeypatch.setattr(
            "sys.argv",
            ["test", "research", "this", "topic"],
        )
        app.run()
        assert app.calls == [("default", "research this topic")]


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class TestHistory:
    def test_session_uses_file_history(self, tmp_path):
        import prompt_toolkit.history as ptkh

        hist_file = tmp_path / "test_history"
        app = RecordingApp(history_file=str(hist_file))
        session = app._create_session()
        assert isinstance(session.history, ptkh.FileHistory)

    def test_session_without_history_file(self):
        app = RecordingApp()
        session = app._create_session()
        assert session.history is not None


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


def _complete(completer: _CommandCompleter, text: str) -> list[str]:
    """Helper: get completion texts for *text*."""
    doc = ptkd.Document(text, len(text))
    event = ptkc.CompleteEvent()
    return [c.text for c in completer.get_completions(doc, event)]


class TestCompletion:
    def test_complete_partial_match(self):
        app = RecordingApp()
        completer = _CommandCompleter(app._commands)
        results = _complete(completer, "/gr")
        assert results == ["/greet"]

    def test_complete_single_match(self):
        app = RecordingApp()
        completer = _CommandCompleter(app._commands)
        results = _complete(completer, "/s")
        assert results == ["/save"]

    def test_complete_slash_lists_all(self):
        app = RecordingApp()
        completer = _CommandCompleter(app._commands)
        results = _complete(completer, "/")
        assert "/help" in results
        assert "/greet" in results
        assert "/save" in results

    def test_complete_plain_text_returns_nothing(self):
        app = RecordingApp()
        completer = _CommandCompleter(app._commands)
        assert _complete(completer, "plain text") == []

    def test_complete_exact_match(self):
        app = RecordingApp()
        completer = _CommandCompleter(app._commands)
        results = _complete(completer, "/help")
        assert "/help" in results

    def test_complete_empty_returns_nothing(self):
        app = RecordingApp()
        completer = _CommandCompleter(app._commands)
        assert _complete(completer, "") == []

    def test_complete_after_space_returns_nothing(self):
        app = RecordingApp()
        completer = _CommandCompleter(app._commands)
        assert _complete(completer, "/save ") == []

    def test_completions_include_descriptions(self):
        app = RecordingApp()
        completer = _CommandCompleter(app._commands)
        doc = ptkd.Document("/gr", 3)
        event = ptkc.CompleteEvent()
        completions = list(completer.get_completions(doc, event))
        assert len(completions) == 1
        assert completions[0].display_meta_text == "Say hello."


# ---------------------------------------------------------------------------
# Preloop / postloop hooks
# ---------------------------------------------------------------------------


class TestHooks:
    def test_preloop_called(self, monkeypatch):
        calls = []

        class HookApp(RecordingApp):
            def preloop(self):
                calls.append("preloop")

        app = HookApp()
        monkeypatch.setattr(
            "prompt_toolkit.PromptSession.prompt",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(EOFError),
        )
        app.cmdloop()
        assert "preloop" in calls

    def test_postloop_called(self, monkeypatch):
        calls = []

        class HookApp(RecordingApp):
            def postloop(self):
                calls.append("postloop")

        app = HookApp()
        monkeypatch.setattr(
            "prompt_toolkit.PromptSession.prompt",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(EOFError),
        )
        app.cmdloop()
        assert "postloop" in calls
