// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

// Expose the interactive Pi session's state and message delivery through local IPC.
import { chmodSync, rmSync } from "node:fs";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

type MessageDeliveryMode = "queue" | "steer";

type MessageRequest = {
  message: string;
  mode: MessageDeliveryMode;
};

type SettledWaiter = {
  after: number;
  resolve: (sequence: number) => void;
};

async function readMessageRequest(request: IncomingMessage): Promise<MessageRequest> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  const value = JSON.parse(Buffer.concat(chunks).toString("utf8")) as Partial<MessageRequest>;
  if (
    typeof value.message !== "string" ||
    value.message.length === 0 ||
    (value.mode !== "queue" && value.mode !== "steer")
  ) {
    throw new Error("message requests require non-empty message and queue or steer mode");
  }
  return { message: value.message, mode: value.mode };
}

function sendJson(response: ServerResponse, status: number, value: object): void {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(value));
}

/** Serve state and message control for one Pi session. */
export default function serveIpc(pi: ExtensionAPI): void {
  const socketFlag = "fore-rsi-ipc-socket";
  const portFlag = "fore-rsi-ipc-port";
  const tokenFlag = "fore-rsi-ipc-token";
  pi.registerFlag(socketFlag, { type: "string", description: "Private IPC socket for this workflow member" });
  pi.registerFlag(portFlag, { type: "string", description: "Private IPC port for this workflow member" });
  pi.registerFlag(tokenFlag, { type: "string", description: "Private IPC token for this workflow member" });

  let server: Server | undefined;
  let socketPath: string | undefined;
  let settledSequence = 0;
  let settledWaiters: SettledWaiter[] = [];

  function waitForSettled(after: number): Promise<number> {
    if (settledSequence > after) return Promise.resolve(settledSequence);
    return new Promise(resolve => settledWaiters.push({ after, resolve }));
  }

  function markSettled(): void {
    settledSequence += 1;
    const ready = settledWaiters.filter(waiter => settledSequence > waiter.after);
    settledWaiters = settledWaiters.filter(waiter => settledSequence <= waiter.after);
    for (const waiter of ready) waiter.resolve(settledSequence);
  }

  function snapshot(ctx: ExtensionContext) {
    const { model, sessionManager } = ctx;
    return {
      record_file: sessionManager.getSessionFile(), session_id: sessionManager.getSessionId(),
      model: model ? `${model.provider}/${model.id}` : null, effort: pi.getThinkingLevel(),
      settled_seq: settledSequence,
    };
  }

  pi.on("agent_settled", () => {
    markSettled();
  });

  pi.on("session_start", async (_event, ctx) => {
    if (ctx.mode !== "tui") return;
    const configuredSocket = pi.getFlag(socketFlag);
    const configuredPort = pi.getFlag(portFlag);
    const configuredToken = pi.getFlag(tokenFlag);
    const port = typeof configuredPort === "string" ? Number.parseInt(configuredPort, 10) : undefined;
    if (
      typeof configuredToken !== "string" ||
      (typeof configuredSocket !== "string" && !Number.isInteger(port))
    ) return;

    if (typeof configuredSocket === "string") {
      rmSync(configuredSocket, { force: true });
      socketPath = configuredSocket;
    }
    const handleRequest = async (request: IncomingMessage, response: ServerResponse): Promise<void> => {
      if (request.headers.authorization !== `Bearer ${configuredToken}`) {
        response.writeHead(403).end();
        return;
      }
      if (request.method === "GET" && request.url === "/state") {
        sendJson(response, 200, snapshot(ctx));
        return;
      }
      if (
        request.method === "GET" &&
        (request.url === "/settled" || request.url?.startsWith("/settled?"))
      ) {
        try {
          const after = Number(new URL(request.url, "http://pi").searchParams.get("after"));
          if (!Number.isSafeInteger(after) || after < 0) {
            throw new Error("settled wait requires a non-negative sequence");
          }
          sendJson(response, 200, { settled_seq: await waitForSettled(after) });
        } catch (error) {
          sendJson(response, 400, { error: String(error) });
        }
        return;
      }
      if (request.method === "POST" && request.url === "/message") {
        try {
          const { message, mode } = await readMessageRequest(request);
          await Promise.resolve(pi.sendUserMessage(message, {
            deliverAs: mode === "queue" ? "followUp" : "steer",
          }));
          sendJson(response, 202, { accepted: true });
        } catch (error) {
          sendJson(response, 400, { error: String(error) });
        }
        return;
      }
      response.writeHead(404).end();
    };
    const listener = createServer((request, response) => {
      void handleRequest(request, response).catch((error: unknown) => {
        if (response.headersSent) response.destroy();
        else sendJson(response, 500, { error: String(error) });
      });
    });
    server = listener;
    await new Promise<void>((resolve, reject) => {
      listener.once("error", reject);
      const listening = () => { listener.off("error", reject); resolve(); };
      if (typeof configuredSocket === "string") listener.listen(configuredSocket, listening);
      else listener.listen({ host: "127.0.0.1", port: port ?? 0 }, listening);
    });
    if (typeof configuredSocket === "string") chmodSync(configuredSocket, 0o600);
  });

  pi.on("session_shutdown", () => {
    settledWaiters = [];
    if (!server) return;
    server.close();
    server = undefined;
    if (socketPath) {
      rmSync(socketPath, { force: true });
      socketPath = undefined;
    }
  });
}
