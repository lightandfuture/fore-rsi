# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Pipe the member's loopback input stream into the Claude mod's native process reader."""

import sys
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

if __name__ == "__main__":
    endpoint = Path(sys.argv[1]).read_text().rsplit("/", 1)[0]
    with build_opener(ProxyHandler({})).open(f"{endpoint}/inputs") as stream:
        for line in stream:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
