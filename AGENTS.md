# General Agent Guidelines

This file provides guidance to code agents when working with code in this repository.

## Project Overview

This project is a Deep Research Agent Terminal User Interface (TUI).

## Development Commands

### Code Quality

```bash
ruff check --fix && ruff format                 # Python linting/formatting
ty check src tests                              # Python type checking
pytest --no-cov --quiet                         # Python tests
```

## Coding Standards

* Avoid using `type: ignore` and other code that disables calls to linters/checkers
  wherever possible.
* In general, functions, classes, etc. should be defined proceed in order from
  higher-level abstractions to lower-level abstractions. Avoid generating code that
  puts lower-level functions first, unless they must be defined first
  (ex: context managers).
* When generating Python function calls that must be wrapped over multiple lines, always
  place each parameter on its own line. The final parameter should be followed with
  a trailing comma, so that Ruff will enforce this.
* When raising exceptions, do not create an unnecessary `msg` variable and pass it
  to the constructor. Just pass the message to the constructor as a literal.
* When using the `typing` library, import the whole module with an alias of `T`, rather
  than importing needed types from the module.
* In general, favor importing packages (with a a short alias when sensible) rather than
  importing names from packages. For example: ```import numpy as np``` is preferred
  over ```from numpy import zeros```. Exceptions to this include `pathlib.Path` and
  imports within `__init__.py` files.
* Here are some preferred module import aliases:
  * dataclasses => dc
  * pytorch => pt
