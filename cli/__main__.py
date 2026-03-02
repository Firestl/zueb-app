"""
Entry point for `python -m cli`.

Run the CLI with:
    .venv/bin/python -m cli --help
"""
import logging
import sys

from cli.main import cli

if __name__ == "__main__":
    cli()
