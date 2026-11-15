# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Process exit handling shared by the installed command and python -m fore_rsi."""

from subprocess import CalledProcessError
import sys

from fore_rsi.main import main


def cli() -> int:
    """Run the application and preserve native command and interruption exit statuses."""
    try:
        main()
    except CalledProcessError as error:
        if error.stderr:
            print(error.stderr, end="", file=sys.stderr)
        elif error.stdout:
            print(error.stdout, end="", file=sys.stderr)
        return error.returncode if error.returncode >= 0 else 128 - error.returncode
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
