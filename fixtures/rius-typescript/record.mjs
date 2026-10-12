// Record what the rius TypeScript SDK itself exports: its native spans and its MCP wrapper.
//
// Usage: node record.mjs <recording.json> [<environment.json>]   (after npm ci)
//
// A control family, the TypeScript counterpart of ../rius-python with the same
// scenarios. The recording is what reaches the SDK's exporter
// (init({ spanExporter })), which is what goes on the wire: spans the SDK
// already normalized, so normalizing them again must change nothing.
//
// MCP scenarios call tools on an in-process MCP server (InMemoryTransport)
// through the SDK's Client.callTool wrapper. No network, no API keys, no model
// calls: a generation's output and usage are whatever the scenario sets.

import {
  SpanKind,
  init,
  observe,
  startAsCurrentGeneration,
  startAsCurrentSpan,
  withSession,
  withUser,
} from "@glassflow-ai/rius";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { InMemorySpanExporter } from "@opentelemetry/sdk-trace-base";
import { z } from "zod";
import { ScriptedProvider, deterministicClock, recordAll } from "../_recording.mjs";

const PACKAGES = [
  "@glassflow-ai/rius",
  "@modelcontextprotocol/sdk",
  "@opentelemetry/api",
  "@opentelemetry/sdk-trace-base",
];

/** The SDK's tracer scope; the only spans this family records. */
const SDK_SCOPE = "rius";

/** The in-memory exporter, read back with only the SDK's own spans. */
class SDKSpans extends InMemorySpanExporter {
  getFinishedSpans() {
    return super
      .getFinishedSpans()
      .filter((span) => (span.instrumentationScope ?? span.instrumentationLibrary)?.name === SDK_SCOPE);
  }
}

// The SDK's spans end on OpenTelemetry's anchored clock, and moments this
// close together can come out in either order from run to run (a parent
// ending before its child). The SDK also measures time to first chunk and
// writes it into a span attribute. Every clock reading advances one tick
// instead (see deterministicClock), so only the order things happened in
// counts, and the measured value is identical across recordings.
deterministicClock();

const exporter = new SDKSpans();
const client = init({
  endpoint: "http://127.0.0.1:9", // never reached: spanExporter replaces the OTLP exporter
  apiKey: "recorder",
  serviceName: "rius-recorder",
  agentName: "weather-agent",
  spanExporter: exporter,
  heartbeat: false,
  partialSpans: false,
});
await client.ready;

const MESSAGES = [
  { role: "system", content: "Answer in one word." },
  { role: "user", content: "Capital of France?" },
];

const WEATHER_TOOL = {
  type: "function",
  function: {
    name: "get_weather",
    description: "Current weather for a city.",
    parameters: {
      type: "object",
      properties: { city: { type: "string" } },
      required: ["city"],
    },
  },
};

const scenarios = {};

scenarios.generation_chat = () =>
  startAsCurrentGeneration(
    {
      model: "gpt-4o-mini",
      provider: "openai",
      input: MESSAGES,
      modelParameters: { temperature: 0.2, max_tokens: 64, seed: 7 },
    },
    async (gen) => {
      gen.setOutput([{ role: "assistant", content: "Paris." }]);
      gen.setModel("gpt-4o-mini-2024-07-18");
      gen.setResponseId("chatcmpl-rec1");
      gen.setFinishReasons("stop");
      gen.setUsage({
        inputTokens: 42,
        outputTokens: 9,
        cacheReadInputTokens: 16,
        reasoningOutputTokens: 3,
      });
    },
  );

scenarios.generation_stream = () =>
  startAsCurrentGeneration(
    { model: "claude-haiku-4-5", provider: "anthropic", input: MESSAGES },
    async (gen) => {
      gen.recordFirstToken();
      gen.setOutput([{ role: "assistant", content: "Paris." }]);
      gen.setFinishReasons("end_turn");
      gen.setUsage({ inputTokens: 20, outputTokens: 4 });
    },
  );

scenarios.generation_error = async () => {
  try {
    await startAsCurrentGeneration(
      { model: "gpt-nope", provider: "openai", input: MESSAGES },
      async () => {
        throw new Error("The model `gpt-nope` does not exist.");
      },
    );
  } catch {
    // The span records the failure; the scenario only needs it to end.
  }
};

const getWeather = observe(
  async function get_weather(city) {
    return "sunny, 22C";
  },
  { kind: SpanKind.TOOL },
);

// An agent turn: a generation that asks for a tool, the tool, a generation that answers.
const weatherAgent = observe(
  async function weatherAgent(question) {
    const asked = [{ role: "user", content: question }];
    const toolCall = {
      role: "assistant",
      tool_calls: [
        {
          id: "call_rec1",
          type: "function",
          function: { name: "get_weather", arguments: '{"city": "Paris"}' },
        },
      ],
    };
    await startAsCurrentGeneration(
      { model: "gpt-4o-mini", provider: "openai", input: asked, tools: [WEATHER_TOOL] },
      async (gen) => {
        gen.setOutput([toolCall]);
        gen.setFinishReasons("tool_calls");
        gen.setUsage({ inputTokens: 60, outputTokens: 12 });
      },
    );
    const result = await getWeather("Paris");
    const answered = [...asked, toolCall, { role: "tool", tool_call_id: "call_rec1", content: result }];
    await startAsCurrentGeneration(
      { model: "gpt-4o-mini", provider: "openai", input: answered, tools: [WEATHER_TOOL] },
      async (gen) => {
        gen.setOutput([{ role: "assistant", content: "Sunny, 22C." }]);
        gen.setFinishReasons("stop");
        gen.setUsage({ inputTokens: 80, outputTokens: 6 });
      },
    );
    return "Sunny, 22C.";
  },
  { kind: SpanKind.AGENT, agentName: "weather-agent" },
);

scenarios.agent_tools = () =>
  withSession("session-rec1", () => withUser("user-rec1", () => weatherAgent("Weather in Paris?")));

scenarios.retrieval = () =>
  startAsCurrentSpan(
    { kind: SpanKind.RETRIEVER, dataSourceId: "product-kb", topK: 2, input: "return policy" },
    async (obs) => {
      obs.setRetrievedDocuments([
        { id: "doc-1", content: "Returns are accepted within 30 days.", score: 0.92 },
        { id: "doc-2", content: "Refunds go to the original card.", score: 0.81 },
      ]);
    },
  );

const planTrip = observe(async function plan_trip(city) {
  return { city, days: 2 };
});

scenarios.chain = () => planTrip("Paris");

function mcpServer() {
  const server = new McpServer({ name: "weather-server", version: "1.0.0" });
  server.registerTool(
    "forecast",
    { description: "Tomorrow's forecast for a city.", inputSchema: { city: z.string() } },
    async ({ city }) => ({ content: [{ type: "text", text: `${city}: sunny, 24C` }] }),
  );
  server.registerTool(
    "broken",
    { description: "Always fails.", inputSchema: { city: z.string() } },
    async () => {
      throw new Error("forecast service unavailable");
    },
  );
  return server;
}

async function callTools(...calls) {
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  const server = mcpServer();
  await server.connect(serverTransport);
  const mcp = new Client({ name: "rius-recorder", version: "1.0.0" });
  await mcp.connect(clientTransport);
  try {
    for (const [name, args] of calls) await mcp.callTool({ name, arguments: args });
  } finally {
    await mcp.close();
    await server.close();
  }
}

scenarios.mcp_tool_call = () => callTools(["forecast", { city: "Paris" }]);

// A tool that throws comes back as an error RESULT (isError), not an
// exception: the span ends ERROR with error.type tool_error.
scenarios.mcp_tool_error = () => callTools(["broken", { city: "Paris" }]);

const forecastAgent = observe(
  async function forecastAgent() {
    await callTools(["forecast", { city: "Paris" }]);
  },
  { kind: SpanKind.AGENT, agentName: "forecast-agent" },
);

scenarios.mcp_in_agent = () => forecastAgent();

// No provider is scripted: the SDK makes no HTTP calls of its own here.
await recordAll(scenarios, exporter, new ScriptedProvider(), PACKAGES, import.meta.url, process.argv.slice(2), () =>
  client.flush(),
);
await client.shutdown();
