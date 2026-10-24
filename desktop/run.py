#!/usr/bin/env python3

from wits_keyboard.logging_config import configure_logging
import sys


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from wits_keyboard.package_smoke import main as smoke
        raise SystemExit(smoke(sys.argv[2]))
    configure_logging()
    from wits_keyboard.app import main

    raise SystemExit(main())
