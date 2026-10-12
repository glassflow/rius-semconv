// Record @arizeai/openinference-instrumentation-anthropic spans against a scripted Anthropic.
//
// Usage: node record.mjs <recording.json> [<environment.json>]   (after npm ci)
//
// Drives @anthropic-ai/sdk, manually instrumented by OpenInference's JS
// Anthropic instrumentation, through a scripted `fetch`. No network, no API
// keys, no rius SDK. The JavaScript counterpart of ../openinference-anthropic,
// with the same scenarios and responses.

import Anthropic from "@anthropic-ai/sdk";
import { AnthropicInstrumentation } from "@arizeai/openinference-instrumentation-anthropic";
import { resourceFromAttributes } from "@opentelemetry/resources";
import {
  BasicTracerProvider,
  InMemorySpanExporter,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import { RECORDER_RESOURCE, ScriptedProvider, json, recordAll, sse } from "../_recording.mjs";

const PACKAGES = [
  "@arizeai/openinference-instrumentation-anthropic",
  "@arizeai/openinference-semantic-conventions",
  "@anthropic-ai/sdk",
  "@opentelemetry/api",
  "@opentelemetry/sdk-trace-base",
];

const MESSAGES = "https://api.anthropic.com/v1/messages";
const MODEL = "claude-haiku-4-5-20251001";

const exporter = new InMemorySpanExporter();
const provider = new BasicTracerProvider({
  resource: resourceFromAttributes(RECORDER_RESOURCE),
  spanProcessors: [new SimpleSpanProcessor(exporter)],
});
new AnthropicInstrumentation({ tracerProvider: provider }).manuallyInstrument(Anthropic);

const script = new ScriptedProvider();
const client = new Anthropic({ apiKey: "sk-ant-test", maxRetries: 0, fetch: script.fetch });

const WEATHER_TOOL = {
  name: "get_weather",
  description: "Current weather for a city",
  input_schema: { type: "object", properties: { city: { type: "string" } }, required: ["city"] },
};

const USAGE = {
  input_tokens: 26,
  output_tokens: 9,
  cache_read_input_tokens: 16,
  cache_creation_input_tokens: 8,
};

const message = (content, stopReason = "end_turn") => ({
  id: "msg_rec1",
  type: "message",
  role: "assistant",
  model: MODEL,
  content,
  stop_reason: stopReason,
  stop_sequence: null,
  usage: USAGE,
});

const TOOL_USE = { type: "tool_use", id: "toolu_rec1", name: "get_weather", input: { city: "Paris" } };

const scenarios = {
  async chat() {
    script.answer(MESSAGES, json(message([{ type: "text", text: "Paris." }])));
    await client.messages.create({
      model: MODEL,
      max_tokens: 64,
      stop_sequences: ["\n\n"],
      system: "Answer in one word.",
      messages: [{ role: "user", content: "Capital of France?" }],
    });
  },

  async chat_stream() {
    const start = { ...message([], null), id: "msg_rec2", usage: { ...USAGE, output_tokens: 1 } };
    script.answer(
      MESSAGES,
      sse([
        ["message_start", { type: "message_start", message: start }],
        ["content_block_start", { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } }],
        ["content_block_delta", { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "Par" } }],
        ["content_block_delta", { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "is." } }],
        ["content_block_stop", { type: "content_block_stop", index: 0 }],
        [
          "message_delta",
          { type: "message_delta", delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 9 } },
        ],
        ["message_stop", { type: "message_stop" }],
      ]),
    );
    const stream = await client.messages.create({
      model: MODEL,
      max_tokens: 64,
      stream: true,
      messages: [{ role: "user", content: "Capital of France?" }],
    });
    for await (const _ of stream) {
      // drain
    }
  },

  async tool_call() {
    script.answer(MESSAGES, json(message([TOOL_USE], "tool_use")));
    await client.messages.create({
      model: MODEL,
      max_tokens: 64,
      tools: [WEATHER_TOOL],
      tool_choice: { type: "auto" },
      messages: [{ role: "user", content: "Weather in Paris?" }],
    });
  },

  async tool_response() {
    script.answer(MESSAGES, json(message([{ type: "text", text: "Sunny, 22C." }])));
    await client.messages.create({
      model: MODEL,
      max_tokens: 64,
      tools: [WEATHER_TOOL],
      messages: [
        { role: "user", content: "Weather in Paris?" },
        { role: "assistant", content: [TOOL_USE] },
        { role: "user", content: [{ type: "tool_result", tool_use_id: "toolu_rec1", content: "sunny, 22C" }] },
      ],
    });
  },

  async error() {
    script.answer(
      MESSAGES,
      json({ type: "error", error: { type: "invalid_request_error", message: "model: claude-nope" } }, 400),
    );
    try {
      await client.messages.create({
        model: "claude-nope",
        max_tokens: 64,
        messages: [{ role: "user", content: "hi" }],
      });
    } catch (error) {
      if (!(error instanceof Anthropic.BadRequestError)) throw error;
      return;
    }
    throw new Error("the scripted 400 did not reject");
  },
};

await recordAll(scenarios, exporter, script, PACKAGES, import.meta.url, process.argv.slice(2));
