// Record @arizeai/openinference-instrumentation-langchain spans against a scripted OpenAI.
//
// Usage: node record.mjs <recording.json> [<environment.json>]   (after npm ci)
//
// Drives @langchain/openai's ChatOpenAI, with OpenInference's JS LangChain
// instrumentation ONLY (manually instrumenting @langchain/core's callback
// manager), through a scripted `fetch` handed to the underlying openai client.
// No network, no API keys, no rius SDK. The JavaScript counterpart of
// ../openinference-langchain, with the same scenarios and responses.

import { LangChainInstrumentation } from "@arizeai/openinference-instrumentation-langchain";
import * as CallbackManagerModule from "@langchain/core/callbacks/manager";
import { AIMessage, HumanMessage, SystemMessage, ToolMessage } from "@langchain/core/messages";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { tool } from "@langchain/core/tools";
import { ChatOpenAI } from "@langchain/openai";
import { resourceFromAttributes } from "@opentelemetry/resources";
import {
  BasicTracerProvider,
  InMemorySpanExporter,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import {
  RECORDER_RESOURCE,
  ScriptedProvider,
  deterministicClock,
  json,
  recordAll,
  sse,
} from "../_recording.mjs";

// LangChain stamps run records with Date.now() while OpenTelemetry reads
// performance.now(); both advance one tick per reading instead (see
// deterministicClock), so the order of close moments cannot vary by rounding.
deterministicClock();

const PACKAGES = [
  "@arizeai/openinference-instrumentation-langchain",
  "@arizeai/openinference-semantic-conventions",
  "@langchain/core",
  "@langchain/openai",
  "@opentelemetry/api",
  "@opentelemetry/sdk-trace-base",
];

const CHAT = "https://api.openai.com/v1/chat/completions";
const MODEL = "gpt-4o-mini";

const exporter = new InMemorySpanExporter();
const provider = new BasicTracerProvider({
  resource: resourceFromAttributes(RECORDER_RESOURCE),
  spanProcessors: [new SimpleSpanProcessor(exporter)],
});
new LangChainInstrumentation({ tracerProvider: provider }).manuallyInstrument(CallbackManagerModule);

const script = new ScriptedProvider();
const llm = (fields = {}) =>
  new ChatOpenAI({
    model: MODEL,
    apiKey: "sk-test",
    maxRetries: 0,
    configuration: { fetch: script.fetch },
    ...fields,
  });

const getWeather = tool(async ({ city }) => `sunny in ${city}`, {
  name: "get_weather",
  description: "Current weather for a city.",
  schema: { type: "object", properties: { city: { type: "string" } }, required: ["city"] },
});

const USAGE = {
  prompt_tokens: 42,
  completion_tokens: 9,
  total_tokens: 51,
  prompt_tokens_details: { cached_tokens: 16, audio_tokens: 0 },
  completion_tokens_details: { reasoning_tokens: 3, audio_tokens: 0 },
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
  function: { name: "get_weather", arguments: JSON.stringify({ city: "Paris" }) },
};

const scenarios = {
  async chat() {
    script.answer(CHAT, json(completion({ role: "assistant", content: "Paris." })));
    await llm({ temperature: 0.2, maxTokens: 64 }).invoke([
      new SystemMessage("Answer in one word."),
      new HumanMessage("Capital of France?"),
    ]);
  },

  async chat_stream() {
    const chunk = (delta, finish = null, usage = null) => ({
      id: "chatcmpl-rec2",
      object: "chat.completion.chunk",
      created: 1700000000,
      model: "gpt-4o-mini-2024-07-18",
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
    for await (const _ of await llm({ streamUsage: true }).stream([new HumanMessage("Capital of France?")])) {
      // drain
    }
  },

  async tool_call() {
    script.answer(
      CHAT,
      json(completion({ role: "assistant", content: null, tool_calls: [TOOL_CALL] }, "tool_calls")),
    );
    await llm()
      .bindTools([getWeather], { tool_choice: "auto" })
      .invoke([new HumanMessage("Weather in Paris?")]);
  },

  async tool_response() {
    script.answer(CHAT, json(completion({ role: "assistant", content: "Sunny, 22C." })));
    await llm()
      .bindTools([getWeather])
      .invoke([
        new HumanMessage("Weather in Paris?"),
        new AIMessage({
          content: "",
          tool_calls: [{ id: "call_rec1", name: "get_weather", args: { city: "Paris" } }],
        }),
        new ToolMessage({ content: "sunny, 22C", tool_call_id: "call_rec1" }),
      ]);
  },

  async chain() {
    script.answer(CHAT, json(completion({ role: "assistant", content: "Paris." })));
    const prompt = ChatPromptTemplate.fromMessages([
      ["system", "Answer in one word."],
      ["human", "Capital of {country}?"],
    ]);
    await prompt.pipe(llm()).invoke({ country: "France" });
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
      await llm({ model: "gpt-nope" }).invoke([new HumanMessage("hi")]);
    } catch {
      return;
    }
    throw new Error("the scripted 400 did not reject");
  },
};

await recordAll(scenarios, exporter, script, PACKAGES, import.meta.url, process.argv.slice(2));
