// Record the Vercel AI SDK v7's spans, as its official @ai-sdk/otel
// integration produces them, against a scripted OpenAI.
//
// Usage: node record.mjs <recording.json> [<environment.json>]   (after npm ci)
//
// ai v7 creates spans only through a registered telemetry integration; this is
// the one the rius SDK registers. Here it is registered by hand with a tracer
// from the recording provider, named as the integration names its own default
// tracer ("gen_ai"), with the options the rius SDK passes: `usage`, so the
// reasoning split the conventions name reaches the spans (it is written only
// under ai.usage.*, and only with that option). No network, no API keys, no
// rius SDK.

import { createOpenAI } from "@ai-sdk/openai";
import { OpenTelemetry } from "@ai-sdk/otel";
import { context } from "@opentelemetry/api";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
import { resourceFromAttributes } from "@opentelemetry/resources";
import {
  BasicTracerProvider,
  InMemorySpanExporter,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import * as ai from "ai";
import { RECORDER_RESOURCE, ScriptedProvider, deterministicClock, recordAll } from "../_recording.mjs";
import { vercelObjectScenarios, vercelScenarios } from "../_vercel.mjs";

deterministicClock();
// What every Node app's provider registers: without an active-context manager
// the AI SDK's spans would not nest under each other.
context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());

const PACKAGES = ["ai", "@ai-sdk/otel", "@ai-sdk/openai", "@opentelemetry/api", "@opentelemetry/sdk-trace-base"];

const exporter = new InMemorySpanExporter();
const provider = new BasicTracerProvider({
  resource: resourceFromAttributes(RECORDER_RESOURCE),
  spanProcessors: [new SimpleSpanProcessor(exporter)],
});
ai.registerTelemetry(new OpenTelemetry({ tracer: provider.getTracer("gen_ai"), usage: true }));

const script = new ScriptedProvider();
const scenarios = {
  ...vercelScenarios({ ai, createOpenAI, script, telemetry: {} }),
  ...vercelObjectScenarios({ ai, createOpenAI, script, telemetry: {} }),
};

await recordAll(scenarios, exporter, script, PACKAGES, import.meta.url, process.argv.slice(2));
