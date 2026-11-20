// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

// Expose the interactive Pi session's settings and live events without opening a second conversation.
import { randomUUID } from "node:crypto";
import { renameSync, writeFileSync } from "node:fs";
import { createServer, type Server, type ServerResponse } from "node:http";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

/** Serve passive observers for the lifetime of this Pi session, independently of tool registration. */
export default function observe(pi: ExtensionAPI): void {
  const flag = "fore-rsi-observation-file";
  pi.registerFlag(flag, { type: "string", description: "Private observation file for this workflow member" });
  const subscribers = new Set<ServerResponse>();
  let server: Server | undefined;
  let endpoint: { port: number; token: string } | undefined;

  function snapshot(ctx: ExtensionContext, forFork = false) {
    const { model, sessionManager } = ctx;
    return {
      session_file: sessionManager.getSessionFile(), session_id: sessionManager.getSessionId(),
      model: model ? `${model.provider}/${model.id}` : null, effort: pi.getThinkingLevel(),
      // /tree can move the active leaf without appending anything to the recorded tree.
      fork_point: forFork ? { leaf: sessionManager.getLeafId(), tip: sessionManager.getEntries().at(-1)?.id ?? null } : undefined,
    };
  }

  function publishSettings(ctx: ExtensionContext): void {
    const file = pi.getFlag(flag);
    if (typeof file !== "string") return;
    const temporary = `${file}.${process.pid}.tmp`;
    writeFileSync(temporary, JSON.stringify({ ...snapshot(ctx, !endpoint), endpoint }), { mode: 0o600 });
    renameSync(temporary, file);
  }

  function emit(event: object): void {
    if (!subscribers.size) return;
    const line = JSON.stringify(event) + "\n";
    for (const client of subscribers) {
      // A stalled observer must not queue unlimited output or delay a model turn.
      if (client.writableNeedDrain) client.destroy();
      else client.write(line);
    }
  }

  pi.on("session_start", async (_event, ctx) => {
    if (ctx.mode !== "tui" || typeof pi.getFlag(flag) !== "string") return;
    const token = randomUUID();
    const listener = createServer((request, response) => {
      if (request.method !== "GET" || request.headers.authorization !== `Bearer ${token}`) {
        response.writeHead(403).end();
        return;
      }
      if (request.url === "/fork-point") {
        response.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(snapshot(ctx, true)));
        return;
      }
      if (request.url !== "/events") { response.writeHead(404).end(); return; }
      response.writeHead(200, { "Content-Type": "application/x-ndjson; charset=utf-8" });
      subscribers.add(response);
      response.on("close", () => subscribers.delete(response));
      response.write(JSON.stringify({ type: "subscribed", session_id: ctx.sessionManager.getSessionId() }) + "\n");
    });
    server = listener;
    await new Promise<void>((resolve, reject) => {
      listener.once("error", reject);
      listener.listen(0, "127.0.0.1", () => { listener.off("error", reject); resolve(); });
    });
    const address = listener.address();
    if (!address || typeof address === "string") throw new Error("Pi observation listener has no loopback port.");
    endpoint = { port: address.port, token };
    publishSettings(ctx);
  });
  pi.on("model_select", (_event, ctx) => { if (endpoint) publishSettings(ctx); });
  pi.on("thinking_level_select", (_event, ctx) => { if (endpoint) publishSettings(ctx); });
  pi.on("session_shutdown", (_event, ctx) => {
    if (!server) return;
    server.close();
    for (const client of subscribers) client.end();
    subscribers.clear();
    server = undefined;
    endpoint = undefined;
    publishSettings(ctx);
  });

  // Project only output and execution events. Pi's message and boundary objects can also contain user history.
  pi.on("message_update", ({ assistantMessageEvent: event }) => {
    if (event.type === "text_delta") emit({ type: event.type, delta: event.delta });
  });
  pi.on("tool_execution_start", ({ type, toolName, toolCallId, parentToolCallId }) => {
    emit({ type, toolName, toolCallId, parentToolCallId });
  });
  pi.on("tool_execution_end", ({ type, toolName, toolCallId, parentToolCallId, isError }) => {
    emit({ type, toolName, toolCallId, parentToolCallId, isError });
  });
  pi.on("message_end", ({ message }) => {
    if (message.role === "assistant" && message.stopReason === "error") emit({ type: "error", message: message.errorMessage });
  });
  pi.on("agent_settled", ({ type, aborted }) => emit({ type, aborted }));
}
