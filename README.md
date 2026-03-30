# DEEPR: Deep Research TUI

## Usage

The easiest way to run the app is with [uvx](https://docs.astral.sh/uv/guides/tools/):

```
uvx git+https://github.com/brentspell/deepr
```

Once you have it running, you can set add your
[Generative Language API](https://console.cloud.google.com/apis/credentials) key with
the `key` command

```
deepr> /key
```

After running a research session, you can save the results to PDF using the `save`
command:

```
deepr> /save my-research.pdf
```

## Development
This project uses the [uv project manager](https://github.com/astral-sh/uv). It can be
installed using
[these instructions](https://docs.astral.sh/uv/getting-started/installation/).

Next, install python, create/activate a virtual environment, and install dependencies:
```
uv venv
. .venv/bin/activate
uv sync
```

You can also optionally set up pre-commit for linting/formatting/etc.
```
pre-commit install
```

Alternatively, the project's checkers can be run manually:
```
ruff check --fix
ruff format
ty check src tests
pytest
```
