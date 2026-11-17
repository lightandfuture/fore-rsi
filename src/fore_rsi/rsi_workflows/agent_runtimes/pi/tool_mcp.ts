// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Register this agent's workflow tools alongside Pi's existing MCP servers. */
export default function registerToolMcp(pi: ExtensionAPI): void {
  const flag = "fore-rsi-mcp-url";
  pi.registerFlag(flag, { type: "string", description: "ForeRSI tool endpoint for this session" });

  // Pi resolves extension flags after loading the extension factory.
  pi.on("session_start", () => {
    const url = pi.getFlag(flag);
    if (typeof url === "string") {
      pi.registerMcpServer("fore_rsi", { url, exposure: "direct" });
    }
  });
}
