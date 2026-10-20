// Record @arizeai/openinference-instrumentation-openai spans against a scripted OpenAI.
//
// Usage: node record.mjs <recording.json> [<environment.json>]   (after npm ci)
//
// Drives the openai client, manually instrumented by OpenInference's JS OpenAI
// instrumentation, through a scripted `fetch` that answers every request with
// realistic OpenAI JSON. No network, no API keys, no rius SDK: these are the raw
// spans. The JavaScript counterpart of ../openinference-openai, with the same
// scenarios and responses, so the two can be compared key for key.

import { OpenAIInstrumentation } from "@arizeai/openinference-instrumentation-openai";
import { resourceFromAttributes } from "@opentelemetry/resources";
import {
  BasicTracerProvider,
  InMemorySpanExporter,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import OpenAI from "openai";
import { PNG_1X1, WAV_SILENT, b64, bigPng, dataUrl } from "../_media.mjs";
import { RECORDER_RESOURCE, ScriptedProvider, json, recordAll, sse } from "../_recording.mjs";

const PACKAGES = [
  "@arizeai/openinference-instrumentation-openai",
  "@arizeai/openinference-semantic-conventions",
  "openai",
  "@opentelemetry/api",
  "@opentelemetry/sdk-trace-base",
];

const CHAT = "https://api.openai.com/v1/chat/completions";
const EMBEDDINGS = "https://api.openai.com/v1/embeddings";

const exporter = new InMemorySpanExporter();
const provider = new BasicTracerProvider({
  resource: resourceFromAttributes(RECORDER_RESOURCE),
  spanProcessors: [new SimpleSpanProcessor(exporter)],
});
const instrumentation = new OpenAIInstrumentation({ tracerProvider: provider });
instrumentation.manuallyInstrument(OpenAI);

const script = new ScriptedProvider();
const client = new OpenAI({ apiKey: "sk-test", maxRetries: 0, fetch: script.fetch });

const WEATHER_TOOL = {
  type: "function",
  function: {
    name: "get_weather",
    description: "Current weather for a city",
    parameters: { type: "object", properties: { city: { type: "string" } }, required: ["city"] },
  },
};

const USAGE = {
  prompt_tokens: 42,
  completion_tokens: 9,
  total_tokens: 51,
  prompt_tokens_details: { cached_tokens: 16, audio_tokens: 0 },
  completion_tokens_details: {
    reasoning_tokens: 3,
    audio_tokens: 0,
    accepted_prediction_tokens: 0,
    rejected_prediction_tokens: 0,
  },
};

const completion = (message, finishReason = "stop") => ({
  id: "chatcmpl-rec1",
  object: "chat.completion",
  created: 1700000000,
  model: "gpt-4o-mini-2024-07-18",
  system_fingerprint: "fp_rec",
  choices: [{ index: 0, message, finish_reason: finishReason }],
  usage: USAGE,
});

const TOOL_CALL = {
  id: "call_rec1",
  type: "function",
  function: { name: "get_weather", arguments: '{"city":"Paris"}' },
};


async function askAboutImage(url) {
  script.answer(CHAT, json(completion({ role: "assistant", content: "A tiny image." })));
  await client.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [
      {
        role: "user",
        content: [
          { type: "text", text: "What is in this image?" },
          { type: "image_url", image_url: { url } },
        ],
      },
    ],
  });
}

const scenarios = {
  async chat() {
    script.answer(CHAT, json(completion({ role: "assistant", content: "Paris." })));
    await client.chat.completions.create({
      model: "gpt-4o-mini",
      temperature: 0.2,
      max_tokens: 64,
      messages: [
        { role: "system", content: "Answer in one word." },
        { role: "user", content: "Capital of France?" },
      ],
    });
  },

  async chat_stream() {
    const chunk = (delta, finish = null, usage = null) => ({
      id: "chatcmpl-rec2",
      object: "chat.completion.chunk",
      created: 1700000000,
      model: "gpt-4o-mini-2024-07-18",
      system_fingerprint: "fp_rec",
      choices: usage ? [] : [{ index: 0, delta, finish_reason: finish }],
      ...(usage ? { usage } : {}),
    });
    script.answer(
      CHAT,
      sse([
        [null, chunk({ role: "assistant", content: "" })],
        [null, chunk({ content: "Par" })],
        [null, chunk({ content: "is." })],
        [null, chunk({}, "stop")],
        [null, chunk({}, null, USAGE)],
        [null, "[DONE]"],
      ]),
    );
    const stream = await client.chat.completions.create({
      model: "gpt-4o-mini",
      stream: true,
      stream_options: { include_usage: true },
      messages: [{ role: "user", content: "Capital of France?" }],
    });
    for await (const _ of stream) {
      // drain
    }
  },

  async tool_call() {
    script.answer(
      CHAT,
      json(completion({ role: "assistant", content: null, tool_calls: [TOOL_CALL] }, "tool_calls")),
    );
    await client.chat.completions.create({
      model: "gpt-4o-mini",
      tools: [WEATHER_TOOL],
      tool_choice: "auto",
      messages: [{ role: "user", content: "Weather in Paris?" }],
    });
  },

  async tool_response() {
    script.answer(CHAT, json(completion({ role: "assistant", content: "Sunny, 22C." })));
    await client.chat.completions.create({
      model: "gpt-4o-mini",
      tools: [WEATHER_TOOL],
      messages: [
        { role: "user", content: "Weather in Paris?" },
        { role: "assistant", content: null, tool_calls: [TOOL_CALL] },
        { role: "tool", tool_call_id: "call_rec1", content: "sunny, 22C" },
      ],
    });
  },

  async error() {
    script.answer(
      CHAT,
      json(
        {
          error: {
            message: "The model `gpt-nope` does not exist.",
            type: "invalid_request_error",
            param: null,
            code: "model_not_found",
          },
        },
        400,
      ),
    );
    try {
      await client.chat.completions.create({
        model: "gpt-nope",
        messages: [{ role: "user", content: "hi" }],
      });
    } catch (error) {
      if (!(error instanceof OpenAI.BadRequestError)) throw error;
      return;
    }
    throw new Error("the scripted 400 did not reject");
  },

  async embeddings() {
    script.answer(
      EMBEDDINGS,
      json({
        object: "list",
        model: "text-embedding-3-small",
        data: [{ object: "embedding", index: 0, embedding: [0.25, -0.5, 0.125] }],
        usage: { prompt_tokens: 5, total_tokens: 5 },
      }),
    );
    await client.embeddings.create({
      model: "text-embedding-3-small",
      input: "Capital of France?",
      encoding_format: "float",
    });
  },
  async image_data_url() {
    await askAboutImage(dataUrl("image/png", PNG_1X1));
  },

  async image_https_url() {
    await askAboutImage("https://example.com/cat.png");
  },

  // Over OpenInference's 32,000-character limit: the instrumentor writes
  // __REDACTED__ instead of the data URL.
  async image_redacted() {
    await askAboutImage(dataUrl("image/png", bigPng(32_000)));
  },

  async input_audio() {
    script.answer(CHAT, json(completion({ role: "assistant", content: "Silence." })));
    await client.chat.completions.create({
      model: "gpt-4o-audio-preview",
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: "What do you hear?" },
            { type: "input_audio", input_audio: { data: b64(WAV_SILENT), format: "wav" } },
          ],
        },
      ],
    });
  },

  async audio_output() {
    const answer = {
      role: "assistant",
      content: null,
      audio: { id: "audio_rec1", data: b64(WAV_SILENT), transcript: "Hello there.", expires_at: 1700003600 },
    };
    script.answer(CHAT, json(completion(answer)));
    await client.chat.completions.create({
      model: "gpt-4o-audio-preview",
      modalities: ["text", "audio"],
      audio: { voice: "alloy", format: "wav" },
      messages: [{ role: "user", content: "Say hello." }],
    });
  },
};

await recordAll(scenarios, exporter, script, PACKAGES, import.meta.url, process.argv.slice(2));
