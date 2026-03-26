import pathlib
import subprocess
import tempfile
import types
import warnings

import cmd2
import google.genai as genai
import google.genai.interactions as gxi
from google.genai._interactions._types import omit as _OMIT
import keyring
import rich.console as rc
import rich.markdown as rm


class DeeprApp(cmd2.Cmd):
    _KEYRING = "deepr"

    def __init__(self) -> None:
        super().__init__(
            persistent_history_file="~/.deepr_history",
        )
        for name in (
            "alias",
            "edit",
            "history",
            "macro",
            "run_pyscript",
            "run_script",
            "set",
            "shell",
            "shortcuts",
        ):
            self.disable_command(name, "This command is not available.")
        self.intro = "Welcome to deepr. Type a prompt to begin research."
        self.prompt = "deepr> "
        self._research_id: str | None = None
        self._reports: list[str] = []

    def sigint_handler(
        self,
        signum: int,
        frame: types.FrameType | None,
    ) -> None:
        if self._research_id is not None:
            super().sigint_handler(signum, frame)
        else:
            raise SystemExit(0)

    def preloop(self) -> None:
        super().preloop()
        existing = keyring.get_password(self._KEYRING, self._KEYRING)
        if not existing:
            self.poutput(
                "No Google GenAI API key found. Use the 'key' command to set one."
            )

    def do_key(self, statement: cmd2.Statement) -> None:
        """Set the Google GenAI API key used for deep research queries.

        Usage: key [API_KEY]

        If no key is provided as an argument, you will be prompted to enter one
        interactively. The key is stored securely in your system keyring.

        You can obtain an API key from https://aistudio.google.com/apikey

        Examples:
            key AIzaSy...                Set a key directly
            key                          Prompt for key input
        """
        key = statement.raw.partition("key")[2].strip()
        if not key:
            key = input("Enter API key: ").strip()
        if not key:
            self.perror("No API key provided.")
            return
        keyring.set_password(self._KEYRING, self._KEYRING, key)
        self.poutput("API key saved to keyring.")

    def do_reset(self, _statement: cmd2.Statement) -> None:
        """Clear the current research conversation and start fresh.

        Usage: reset

        Discards all follow-up context and accumulated reports from the current
        session. After resetting, your next query will begin a new independent
        research conversation.

        This does not affect your saved API key or command history.
        """
        self._research_id = None
        self._reports.clear()
        self.prompt = "deepr> "
        self.poutput("Conversation cleared. Type a prompt to begin new research.")

    def do_save(self, statement: cmd2.Statement) -> None:
        """Export the current research reports to a PDF file.

        Usage: save [FILENAME]

        Combines all reports from the current conversation into a single PDF
        using pandoc. If no filename is given, defaults to 'deepr_report.pdf'
        in the current directory.

        Requires pandoc to be installed (https://pandoc.org/).

        Examples:
            save                         Save to deepr_report.pdf
            save my_research.pdf         Save to my_research.pdf
            save ~/reports/topic.pdf     Save to an absolute path
        """
        if not self._reports:
            self.perror("No research to export. Run a query first.")
            return

        filename = statement.raw.partition("save")[2].strip() or "deepr_report.pdf"
        output_path = pathlib.Path(filename).resolve()

        combined = "\n\n---\n\n".join(self._reports)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md") as tmp:
            tmp.write(combined)
            tmp.flush()

            try:
                result = subprocess.run(
                    ["pandoc", tmp.name, "-o", str(output_path)],
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError:
                self.perror(
                    "pandoc is not installed. Install it from https://pandoc.org/"
                )
                return

        if result.returncode != 0:
            self.perror(f"pandoc failed: {result.stderr.strip()}")
            return

        self.poutput(f"PDF saved to {output_path}")

    def default(self, statement: cmd2.Statement) -> None:
        text = statement.raw.strip()
        if not text:
            return

        client = genai.Client(
            api_key=keyring.get_password(self._KEYRING, self._KEYRING),
        )

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="Interactions usage is experimental"
            )
            interaction = client.interactions.create(
                input=text,
                agent="deep-research-pro-preview-12-2025",
                agent_config={"type": "deep-research", "thinking_summaries": "auto"},
                background=True,
                previous_interaction_id=(
                    self._research_id if self._research_id is not None else _OMIT
                ),
            )

        console = rc.Console(width=120)
        console.print()
        report_text = ""
        streaming_report = False

        self._research_id = interaction.id
        try:
            with console.status("Researching...") as status:
                stream = client.interactions.get(interaction.id, stream=True)
                for event in stream:
                    if isinstance(event, gxi.ContentDelta):
                        delta = event.delta
                        if delta.type == "thought_summary":
                            content = getattr(delta, "content", None)
                            if content is not None and hasattr(content, "text"):
                                status.update(f"Thinking: {content.text}")
                        elif delta.type == "google_search_call":
                            queries = getattr(delta, "arguments", None)
                            if queries is not None:
                                query_list = getattr(queries, "queries", None) or []
                                if query_list:
                                    status.update(f"Searching: {query_list[0]}")
                        elif delta.type == "text":
                            if not streaming_report:
                                streaming_report = True
                                status.stop()
                            report_text += getattr(delta, "text", "")
                    elif isinstance(event, gxi.InteractionStatusUpdate):
                        if event.status == "failed":
                            status.stop()
                            self.perror(f"Research failed (status: {event.status})")
                            return
                        if not streaming_report:
                            status.update(f"Researching... ({event.status})")
                    elif isinstance(event, gxi.ErrorEvent):
                        status.stop()
                        self.perror(f"Research error: {event}")
                        return
        except KeyboardInterrupt:
            client.interactions.cancel(interaction.id)
            self._research_id = None
            self.poutput("\nResearch cancelled.")
            return

        if report_text:
            console.print(rm.Markdown(report_text))
            self._reports.append(report_text)
            self.prompt = "deepr (follow-up)> "


def main() -> None:
    app = DeeprApp()
    app.cmdloop()


if __name__ == "__main__":
    main()
