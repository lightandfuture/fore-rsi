// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

let endpoint;
let activeTurn;
let steeredTurn;
let workflowPrompt = false;

async function report($, event) {
  if (!endpoint) return;
  const response = await $.http.fetch(`${endpoint}/turn`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: await $.session.id(), ...event }),
  });
  if (response.status !== 200) throw new Error(`ForeRSI turn endpoint returned HTTP ${response.status}`);
}

// The pipe blocks until the workflow has input. Its process belongs to the
// native mod and is reaped by Claude Code when the session or mod closes.
async function readInputs($, addressFile) {
  const python = await $.env.get('FORE_RSI_PYTHON');
  const bridge = `${$.plugin.root}/hooks/input_stream.py`;
  let buffer = '';
  for await (const chunk of $.process.spawn({ argv: [python, '-I', '-S', bridge, addressFile] })) {
    if (chunk.stream !== 'stdout') continue;
    buffer += chunk.text;
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      const { mode, text } = JSON.parse(line);
      try {
        const turn = activeTurn;
        if (mode === 'steer' && turn) {
          steeredTurn = turn;
          try { await $.turn.abort({ turnId: turn }); }
          catch (error) {
            steeredTurn = undefined;
            if (activeTurn === turn) throw error;
          }
        }
        const result = await $.prompt.submit({ text, asUser: true });
        if (result.drop) await report($, { event: 'failed', error: result.drop });
      } catch (error) {
        await report($, { event: 'failed', error: String(error) });
      }
    }
  }
}

/** Connect workflow input and native turn events to this visible conversation. */
export function register(on) {
  on('session.start', async ($, e, next) => {
    const started = await next(e);
    const file = await $.env.get('FORE_RSI_MCP_ADDRESS_FILE');
    if (file) {
      endpoint = (await $.fs.read(file)).trim().replace(/\/mcp$/, '');
      await report($, { event: 'session', transcript: (await $.session.info()).transcriptPath });
      void readInputs($, file).catch(error => report($, { event: 'failed', error: String(error) }));
    }
    return started;
  });
  // The engine commits the prompt before starting its turn. Use its stamped
  // origin: a person can submit identical text, and another mod can rewrite it.
  on('session.append', { door: 'prompt' }, ($, e, next) => {
    if (!e.agentId && e.origin.kind === 'plugin' && e.origin.name === $.plugin.name) workflowPrompt = true;
    return next(e);
  });
  on('turn.start', async ($, e, next) => {
    if (!e.agentId) {
      activeTurn = e.turnId;
      const workflow = workflowPrompt;
      workflowPrompt = false;
      await report($, { event: 'start', turnId: e.turnId, workflow });
    }
    return next(e);
  });
  on('turn.complete', async ($, e, next) => {
    if (!e.agentId) {
      if (activeTurn === e.turnId) activeTurn = undefined;
      const reason = steeredTurn === e.turnId && e.isAborted ? 'steered' : e.reason;
      if (steeredTurn === e.turnId) steeredTurn = undefined;
      await report($, { event: 'complete', turnId: e.turnId, reason });
    }
    return next(e);
  });
}
