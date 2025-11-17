#!/usr/bin/env python3

"""Module entry point for the reorganized Kokoro TTS service."""

from .. import main as service_main


def run() -> None:
    """Start the CLI entrypoint when executed as a module."""
    service_main.main()


if __name__ == "__main__":
    run()
