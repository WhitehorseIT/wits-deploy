#!/usr/bin/env python3

from wits_keyboard.logging_config import configure_logging


if __name__ == "__main__":
    configure_logging()
    from wits_keyboard.app import main

    raise SystemExit(main())
