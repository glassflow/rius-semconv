// Record the Vercel AI SDK v6's own telemetry (the ai.* dialect) against a
// scripted OpenAI.
//
// Usage: node record.mjs <recording.json> [<environment.json>]   (after npm ci)
//
// ai v6 traces a call when it is given experimental_telemetry with a tracer.
// These are the raw ai.* spans: the rius SDK's normalizer maps them, so its
// processor chain is part of what produces the expected result, not of the
// recording. No network, no API keys, no rius SDK.

import { createOpenAI } from "@ai-sdk/openai";
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
import { vercelScenarios } from "../_vercel.mjs";

deterministicClock();
// What every Node app's provider registers: without an active-context manager
// the AI SDK's spans would not nest under each other.
context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());

const PACKAGES = ["ai", "@ai-sdk/openai", "@opentelemetry/api", "@opentelemetry/sdk-trace-base"];

const exporter = new InMemorySpanExporter();
const provider = new BasicTracerProvider({
  resource: resourceFromAttributes(RECORDER_RESOURCE),
  spanProcessors: [new SimpleSpanProcessor(exporter)],
});

const script = new ScriptedProvider();
const scenarios = vercelScenarios({
  ai,
  createOpenAI,
  script,
  telemetry: { experimental_telemetry: { isEnabled: true, tracer: provider.getTracer("ai") } },
});

await recordAll(scenarios, exporter, script, PACKAGES, import.meta.url, process.argv.slice(2));
