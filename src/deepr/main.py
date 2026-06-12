import pathlib
import subprocess
import tempfile
import warnings

import google.genai as genai
import google.genai.interactions as gxi
import google.genai._interactions as gxii
import keyring
import rich.markdown as rm

import deepr.latex as dl
from deepr.command import CommandApp, command


class DeeprApp(CommandApp):
    _KEYRING = "deepr"
    _STREAM_READ_TIMEOUT = 60.0

    def __init__(self) -> None:
        super().__init__(
            prompt="deepr> ",
            history_file="~/.deepr_history",
            intro="Welcome to deepr. Type a prompt to begin research.",
            prog="deepr",
            description="Deep Research Agent",
            console_width=120,
        )
        self._research_id: str | None = None
        self._reports: list[str] = []

    def preloop(self) -> None:
        existing = keyring.get_password(self._KEYRING, self._KEYRING)
        if not existing:
            self.poutput("No Google GenAI API key found. Use '/key' to set one.")

    @command()
    def cmd_key(self, args: str) -> None:
        """Set the Google GenAI API key used for deep research queries.

        Usage: /key [API_KEY]

        If no key is provided as an argument, you will be prompted to enter one
        interactively. The key is stored securely in your system keyring.

        You can obtain an API key from https://aistudio.google.com/apikey

        Examples:
            /key AIzaSy...               Set a key directly
            /key                         Prompt for key input
        """
        key = args.strip()
        if not key:
            key = input("Enter API key: ").strip()
        if not key:
            self.perror("No API key provided.")
            return
        keyring.set_password(self._KEYRING, self._KEYRING, key)
        self.poutput("API key saved to keyring.")

    @command()
    def cmd_reset(self, args: str) -> None:
        """Clear the current research conversation and start fresh.

        Usage: /reset

        Discards all follow-up context and accumulated reports from the current
        session. After resetting, your next query will begin a new independent
        research conversation.

        This does not affect your saved API key or command history.
        """
        self._research_id = None
        self._reports.clear()
        self._prompt = "deepr> "
        self.poutput("Conversation cleared. Type a prompt to begin new research.")

    @command()
    def cmd_save(self, args: str) -> None:
        """Export the current research reports to a PDF file.

        Usage: /save [FILENAME]

        Combines all reports from the current conversation into a single PDF
        using pandoc. If no filename is given, defaults to 'deepr_report.pdf'
        in the current directory.

        Requires pandoc to be installed (https://pandoc.org/).

        Examples:
            /save                        Save to deepr_report.pdf
            /save my_research.pdf        Save to my_research.pdf
            /save ~/reports/topic.pdf    Save to an absolute path
        """
        if not self._reports:
            self.perror("No research to export. Run a query first.")
            return

        filename = args.strip() or "deepr_report.pdf"
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

    def default(self, text: str) -> None:
        if not text:
            return

        client = genai.Client(
            api_key=keyring.get_password(self._KEYRING, self._KEYRING),
        )

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Interactions usage is experimental",
            )
            interaction = client.interactions.create(
                input=text,
                agent="deep-research-max-preview-04-2026",
                agent_config={"type": "deep-research", "thinking_summaries": "auto"},
                background=True,
                previous_interaction_id=(
                    self._research_id
                    if self._research_id is not None
                    else gxii._types.omit
                ),
            )

        console = self.console
        console.print()
        report_text = ""
        last_event_id = gxii._types.omit

        self._research_id = interaction.id
        try:
            with console.status("Researching...") as status:
                while True:
                    try:
                        stream = client.interactions.get(
                            interaction.id,
                            stream=True,
                            last_event_id=last_event_id,
                            timeout=self._STREAM_READ_TIMEOUT,
                        )
                        for event in stream:
                            eid = getattr(event, "event_id", None)
                            if eid:
                                last_event_id = eid

                            if isinstance(event, gxi.StepDelta):
                                delta = event.delta
                                if delta.type == "thought_summary":
                                    content = getattr(delta, "content", None)
                                    if content is not None and hasattr(content, "text"):
                                        status.update(f"Thinking: {content.text}")
                                elif delta.type == "google_search_call":
                                    queries = getattr(delta, "arguments", None)
                                    if queries is not None:
                                        query_list = (
                                            getattr(queries, "queries", None) or []
                                        )
                                        if query_list:
                                            status.update(f"Searching: {query_list[0]}")
                            elif isinstance(event, gxi.InteractionStatusUpdate):
                                if event.status in (
                                    "completed",
                                    "failed",
                                    "cancelled",
                                    "incomplete",
                                ):
                                    break
                                status.update(f"Researching... ({event.status})")
                            elif isinstance(event, gxi.InteractionCompletedEvent):
                                break
                            elif isinstance(event, gxi.ErrorEvent):
                                break
                    except Exception:
                        # ignore any streaming progress errors
                        pass

                    current = client.interactions.get(interaction.id)
                    if current.status != "in_progress":
                        if current.status != "completed":
                            self.perror(f"Research ended with status: {current.status}")
                        else:
                            report_text = self._extract_report(current)
                        break
        except KeyboardInterrupt:
            try:
                client.interactions.cancel(interaction.id)
            except Exception:
                pass
            self._research_id = None
            self.poutput("\nResearch cancelled.")
            return

        if report_text:
            console.print(rm.Markdown(dl.latex_to_unicode(report_text)))
            self._reports.append(report_text)
            self._prompt = "deepr (follow-up)> "
            self.notify("Research complete")

    @staticmethod
    def _extract_report(interaction: gxi.Interaction) -> str:
        # The final report is emitted as the last model_output step; concatenate
        # its text content blocks (the new "steps" schema replaces the old
        # top-level "outputs" list).
        for step in reversed(interaction.steps or []):
            if isinstance(step, gxi.ModelOutputStep):
                return "".join(
                    block.text
                    for block in (step.content or [])
                    if isinstance(block, gxi.TextContent)
                )
        return ""


def main() -> None:
    app = DeeprApp()
    app.run()


if __name__ == "__main__":
    main()
