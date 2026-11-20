// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

import { readFileSync, watch, type FSWatcher } from "node:fs";
import { basename, dirname } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Rebind the member's tools when its workflow host resumes on another local port. */
export default function registerToolMcp(pi: ExtensionAPI): void {
  const flag = "fore-rsi-mcp-file";
  pi.registerFlag(flag, { type: "string", description: "File containing this member's ForeRSI tool endpoint" });

  let watcher: FSWatcher | undefined;
  let registered: string | undefined;
  let connecting = false;
  function refresh(file: string): void {
    let url: string | undefined;
    try {
      url = readFileSync(file, "utf8").trim();
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    if (url === registered) return;
    if (url === undefined) {
      pi.unregisterMcpServer("fore_rsi");
    } else {
      const address = new URL(url);
      if (address.protocol !== "http:" || address.hostname !== "127.0.0.1") {
        throw new Error("ForeRSI tools require a local workflow host.");
      }
      pi.registerMcpServer("fore_rsi", { url, exposure: "direct" });
    }
    connecting = url !== undefined;
    registered = url;
  }

  pi.on("session_start", (_event, ctx) => {
    const file = pi.getFlag(flag);
    if (typeof file !== "string") return;
    watcher?.close();
    // The host atomically replaces the file. Watch its directory, not the old inode.
    watcher = watch(dirname(file), { persistent: false }, (_event, name) => {
      if (name !== null && name !== basename(file)) return;
      try { refresh(file); } catch { ctx.ui.notify("Could not read the ForeRSI tool address.", "error"); }
    });
    refresh(file);
  });
  pi.on("session_shutdown", () => {
    watcher?.close();
    registered = undefined;
    connecting = false;
  });
  pi.on("input", async (_event, ctx) => {
    const file = pi.getFlag(flag);
    if (typeof file === "string") refresh(file);
    if (connecting) {
      // Pi waits for its initial direct tools, but a live host replacement also needs discovery.
      const deadline = Date.now() + 10_000;
      do {
        await delay(25);
        if (pi.getActiveTools().some(name => name.startsWith("mcp__fore_rsi__"))) connecting = false;
      } while (connecting && Date.now() < deadline);
      if (connecting) ctx.ui.notify("ForeRSI tools are still connecting.", "warning");
    }
    return { action: "continue" };
  });
}
