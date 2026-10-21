import sys

from .cli import main

if __name__ == "__main__":
    # Patches are line-exact: Windows' default "\n" -> "\r\n" translation on
    # redirected output would add a carriage return to every line, and the
    # locale encoding could not represent every character read as UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    raise SystemExit(main())
