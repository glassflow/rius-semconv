/**
 * Write a recording's expected result from the TypeScript SDK's normalizer.
 *
 *   npx tsx tools/expect_typescript.mts --sdk <rius-sdk-typescript checkout> \
 *     --sdk-commit <sha> fixtures/<family>/<recording>.json ...
 *
 * For the families only the TypeScript SDK covers (the Vercel AI SDK), the
 * TypeScript SDK is the reference. The SDK is bundled into a single file that
 * exports only its public API, so this imports its SOURCE from a checkout
 * (with node_modules installed), which is why it runs under tsx.
 *
 * Each scenario is replayed through a real tracer, so the SDK's processors see
 * a span start and end exactly as they do live:
 *
 * - an id generator hands out the recorded trace and span ids, so parent links
 *   and numbering survive;
 * - the processor chain mirrors the SDK's: the Vercel ai.* transform first
 *   (the `vercel-ai` registry entry, which acts only on ai.* dialect spans),
 *   then the NormalizingSpanProcessor;
 * - when the manifest marks the family `replay.aggregating_producer`, spans are
 *   started through the SDK's `aggregatingTracer`, as the SDK starts
 *   @ai-sdk/otel's spans live, so the aggregate-usage move applies.
 *
 * The output keeps the recording's ids and times and is written next to it as
 * <recording>.expected.json. Review it by hand before committing it.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const { values, positionals } = parseArgs({
  options: { sdk: { type: "string" }, "sdk-commit": { type: "string" } },
  allowPositionals: true,
});
if (!values.sdk || !values["sdk-commit"] || positionals.length === 0) {
  console.error("usage: expect_typescript.mts --sdk <checkout> --sdk-commit <sha> <recording.json>...");
  process.exit(2);
}
const sdk = resolve(values.sdk);
const fromSdk = createRequire(join(sdk, "package.json"));
const load = (specifier: string) => import(pathToFileURL(fromSdk.resolve(specifier)).href);

// The SDK's own copies of the OpenTelemetry packages, so every object the
// processors see comes from the same module instances the SDK was built with.
const api = await load("@opentelemetry/api");
const base = await load("@opentelemetry/sdk-trace-base");
const resources = await load("@opentelemetry/resources");
const { NormalizingSpanProcessor } = await import(pathToFileURL(join(sdk, "src/normalize.ts")).href);
const { REGISTRY } = await import(pathToFileURL(join(sdk, "src/instrumentation.ts")).href);
const { aggregatingTracer } = await import(pathToFileURL(join(sdk, "src/aggregatedUsage.ts")).href);
const { scenarioJson } = await import(
  pathToFileURL(resolve(dirname(new URL(import.meta.url).pathname), "../fixtures/_recording.mjs")).href
);
const sdkVersion: string = JSON.parse(readFileSync(join(sdk, "package.json"), "utf8")).version;

const KINDS: Record<string, number> = {
  SPAN_KIND_INTERNAL: 0,
  SPAN_KIND_SERVER: 1,
  SPAN_KIND_CLIENT: 2,
  SPAN_KIND_PRODUCER: 3,
  SPAN_KIND_CONSUMER: 4,
};
const STATUS: Record<string, number> = { STATUS_CODE_UNSET: 0, STATUS_CODE_OK: 1, STATUS_CODE_ERROR: 2 };

type AnyValue = {
  stringValue?: string;
  boolValue?: boolean;
  intValue?: string;
  doubleValue?: number;
  arrayValue?: { values?: AnyValue[] };
};
type KeyValue = { key: string; value: AnyValue };

function anyValue(v: AnyValue): unknown {
  if (v.stringValue !== undefined) return v.stringValue;
  if (v.boolValue !== undefined) return v.boolValue;
  if (v.intValue !== undefined) return Number(v.intValue);
  if (v.doubleValue !== undefined) return v.doubleValue;
  if (v.arrayValue !== undefined) return (v.arrayValue.values ?? []).map(anyValue);
  throw new Error(`unsupported attribute value: ${JSON.stringify(v)}`);
}

const attrs = (items: KeyValue[] = []) => Object.fromEntries(items.map((a) => [a.key, anyValue(a.value)]));
const hr = (ns: string): [number, number] => {
  const n = BigInt(ns);
  return [Number(n / 1_000_000_000n), Number(n % 1_000_000_000n)];
};

/** Hands out the recorded ids, in the order the tracer asks for them. */
class ReplayIds {
  traceIds: string[] = [];
  spanIds: string[] = [];
  generateTraceId = () => this.traceIds.shift() as string;
  generateSpanId = () => this.spanIds.shift() as string;
}

async function replay(scenario: any, aggregating: boolean): Promise<unknown> {
  const ids = new ReplayIds();
  const sink = new base.InMemorySpanExporter();
  const vercel = await REGISTRY.find((e: { name: string }) => e.name === "vercel-ai").load();
  const provider = new base.BasicTracerProvider({
    resource: resources.resourceFromAttributes(attrs(scenario.resource?.attributes)),
    idGenerator: ids,
    spanProcessors: [
      ...(vercel ? [vercel] : []),
      new NormalizingSpanProcessor(),
      new base.SimpleSpanProcessor(sink),
    ],
  });

  const live = new Map<string, any>();
  for (const { scope, span: d } of scenario.spans) {
    // A root asks for a trace id; every span asks for a span id.
    if (!d.parentSpanId) ids.traceIds.push(d.traceId);
    ids.spanIds.push(d.spanId);
    let tracer = provider.getTracer(scope.name, scope.version || undefined);
    if (aggregating) tracer = aggregatingTracer(tracer);
    const parent = d.parentSpanId ? live.get(d.parentSpanId) : undefined;
    const ctx = parent ? api.trace.setSpan(api.ROOT_CONTEXT, parent) : api.ROOT_CONTEXT;
    const span = tracer.startSpan(
      d.name,
      { kind: KINDS[d.kind ?? "SPAN_KIND_INTERNAL"], attributes: attrs(d.attributes), startTime: hr(d.startTimeUnixNano) },
      ctx,
    );
    for (const e of d.events ?? []) span.addEvent(e.name, attrs(e.attributes), hr(e.timeUnixNano));
    const code = STATUS[d.status?.code ?? "STATUS_CODE_UNSET"];
    if (code) span.setStatus({ code, ...(d.status?.message ? { message: d.status.message } : {}) });
    live.set(d.spanId, span);
  }
  const byEnd = [...scenario.spans].sort((a: any, b: any) =>
    BigInt(a.span.endTimeUnixNano) < BigInt(b.span.endTimeUnixNano) ? -1 : 1,
  );
  for (const { span: d } of byEnd) live.get(d.spanId).end(hr(d.endTimeUnixNano));
  await provider.forceFlush();
  return scenarioJson(scenario.scenario, sink.getFinishedSpans(), { canonicalize: false });
}

for (const path of positionals.map((p) => resolve(p))) {
  const manifest = JSON.parse(readFileSync(join(dirname(path), "manifest.json"), "utf8"));
  const entry = manifest.recordings?.[basename(path)];
  if (!entry) throw new Error(`${basename(path)} is not listed in its manifest.json`);
  const aggregating = Boolean(entry.replay?.aggregating_producer);
  const recording = JSON.parse(readFileSync(path, "utf8"));
  const out = [];
  for (const scenario of recording.recordings) out.push(await replay(scenario, aggregating));
  const target = path.replace(/\.json$/, ".expected.json");
  const document = {
    normalizer: { package: "@glassflow-ai/rius", version: sdkVersion, commit: values["sdk-commit"] },
    recordings: out,
  };
  writeFileSync(target, `${JSON.stringify(document, null, 2)}\n`);
  console.log(`wrote ${target}`);
}
