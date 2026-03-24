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
        super().__init__()
        self.intro = "Welcome to deepr. Type a prompt to begin research."
        self.prompt = "deepr> "
        self._last_interaction_id: str | None = None

    def preloop(self) -> None:
        super().preloop()
        existing = keyring.get_password(self._KEYRING, self._KEYRING)
        if not existing:
            self.poutput(
                "No Google GenAI API key found. Use the 'key' command to set one."
            )

    def do_key(self, statement: cmd2.Statement) -> None:
        """Set the Google GenAI API key."""
        key = statement.raw.partition("key")[2].strip()
        if not key:
            key = input("Enter API key: ").strip()
        if not key:
            self.perror("No API key provided.")
            return
        keyring.set_password(self._KEYRING, self._KEYRING, key)
        self.poutput("API key saved to keyring.")

    def do_new(self, _statement: cmd2.Statement) -> None:
        """Start a new research conversation, clearing follow-up context."""
        self._last_interaction_id = None
        self.prompt = "deepr> "
        self.poutput("Conversation cleared. Type a prompt to begin new research.")

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
                    self._last_interaction_id
                    if self._last_interaction_id is not None
                    else _OMIT
                ),
            )

        console = rc.Console(width=120)
        console.print()
        report_text = ""
        streaming_report = False

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
            self.poutput("\nResearch cancelled.")
            return

        if report_text:
            console.print(rm.Markdown(report_text))
            self._last_interaction_id = interaction.id
            self.prompt = "deepr (follow-up)> "


def main() -> None:
    app = DeeprApp()
    app.cmdloop()


if __name__ == "__main__":
    main()
