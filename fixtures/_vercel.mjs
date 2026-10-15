// The Vercel AI SDK scenarios, shared by ./vercel-ai-otel (ai v7 through
// @ai-sdk/otel) and ./vercel-ai-v5 (ai v5's own ai.* telemetry).
//
// Each family installs its own `ai` and `@ai-sdk/openai` (different majors), so
// the modules are passed in rather than imported here, and `telemetry` is what
// each call needs to be traced: nothing for v7 (registered once), and
// `experimental_telemetry` for v5. Models go through `openai.chat(...)`, the
// chat-completions API, so the scripted responses are the same OpenAI JSON the
// other families use.

import { json, sse } from "./_recording.mjs";

const CHAT = "https://api.openai.com/v1/chat/completions";
const EMBEDDINGS = "https://api.openai.com/v1/embeddings";

const USAGE = {
  prompt_tokens: 42,
  completion_tokens: 9,
  total_tokens: 51,
  prompt_tokens_details: { cached_tokens: 16, audio_tokens: 0 },
  completion_tokens_details: { reasoning_tokens: 3, audio_tokens: 0 },
};

const completion = (message, finishReason = "stop", id = "chatcmpl-rec1", usage = USAGE) => ({
  id,
  object: "chat.completion",
  created: 1700000000,
  model: "gpt-4o-mini-2024-07-18",
  system_fingerprint: "fp_rec",
  choices: [{ index: 0, message, finish_reason: finishReason }],
  usage,
});

export function vercelScenarios({ ai, createOpenAI, script, telemetry }) {
  const openai = createOpenAI({ apiKey: "sk-test", fetch: script.fetch });
  const model = (name = "gpt-4o-mini") => openai.chat(name);

  return {
    async generate_text() {
      script.answer(CHAT, json(completion({ role: "assistant", content: "Paris." })));
      await ai.generateText({
        model: model(),
        system: "Answer in one word.",
        prompt: "Capital of France?",
        temperature: 0.2,
        maxOutputTokens: 64,
        maxRetries: 0,
        ...telemetry,
      });
    },

    async stream_text() {
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
      const result = ai.streamText({
        model: model(),
        prompt: "Capital of France?",
        maxRetries: 0,
        ...telemetry,
      });
      for await (const _ of result.textStream) {
        // drain
      }
    },

    // Two model calls in one run, with the tool executed between them: the
    // shape where the run's usage, reported on each call and again on the
    // run's own span, is counted twice by a backend that sums usage across
    // spans. The calls report 24/51 and 91/15 tokens.
    async tool_loop() {
      script.answer(
        CHAT,
        json(
          completion(
            {
              role: "assistant",
              content: null,
              tool_calls: [
                {
                  id: "call_rec1",
                  type: "function",
                  function: { name: "get_weather", arguments: '{"city":"Paris"}' },
                },
              ],
            },
            "tool_calls",
            "chatcmpl-rec1",
            { prompt_tokens: 24, completion_tokens: 51, total_tokens: 75 },
          ),
        ),
        json(
          completion({ role: "assistant", content: "Sunny, 22C." }, "stop", "chatcmpl-rec2", {
            prompt_tokens: 91,
            completion_tokens: 15,
            total_tokens: 106,
          }),
        ),
      );
      await ai.generateText({
        model: model(),
        prompt: "Weather in Paris?",
        stopWhen: ai.stepCountIs(2),
        maxRetries: 0,
        tools: {
          get_weather: ai.tool({
            description: "Current weather for a city",
            inputSchema: ai.jsonSchema({
              type: "object",
              properties: { city: { type: "string" } },
              required: ["city"],
            }),
            execute: async () => "sunny, 22C",
          }),
        },
        ...telemetry,
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
        await ai.generateText({ model: model("gpt-nope"), prompt: "hi", maxRetries: 0, ...telemetry });
      } catch {
        return;
      }
      throw new Error("the scripted 400 did not reject");
    },

    async embed() {
      script.answer(
        EMBEDDINGS,
        json({
          object: "list",
          model: "text-embedding-3-small",
          data: [{ object: "embedding", index: 0, embedding: [0.25, -0.5, 0.125] }],
          usage: { prompt_tokens: 5, total_tokens: 5 },
        }),
      );
      await ai.embed({
        model: openai.embedding("text-embedding-3-small"),
        value: "Capital of France?",
        maxRetries: 0,
        ...telemetry,
      });
    },
  };
}

const RERANK = "https://api.cohere.com/v2/rerank";

/**
 * The rerank call, which only v6 traces: v5 has no rerank, and v7's goes
 * through @ai-sdk/otel like every other v7 call. No OpenAI model reranks, so
 * it runs against Cohere's, whose answer is the same scripted JSON shape.
 */
export function vercelRerankScenarios({ ai, createCohere, script, telemetry }) {
  const cohere = createCohere({ apiKey: "co-test", fetch: script.fetch });

  return {
    async rerank() {
      script.answer(
        RERANK,
        json({
          id: "rerank-rec1",
          results: [
            { index: 2, relevance_score: 0.875 },
            { index: 0, relevance_score: 0.25 },
          ],
          meta: { api_version: { version: "2" }, billed_units: { search_units: 1 } },
        }),
      );
      await ai.rerank({
        model: cohere.reranking("rerank-v3.5"),
        query: "Capital of France?",
        documents: ["Berlin is the capital of Germany.", "Madrid is in Spain.", "Paris is the capital of France."],
        topN: 2,
        maxRetries: 0,
        ...telemetry,
      });
    },
  };
}

// generateObject, recorded by ./vercel-ai-otel only: the v5 and v6 recordings
// were made without it, and adding a scenario to them would re-record both.
// Deprecated in v7 in favour of generateText with an `output` setting, but
// still exported and still traced as its own operation (ai.generateObject).
export function vercelObjectScenarios({ ai, createOpenAI, script, telemetry }) {
  const openai = createOpenAI({ apiKey: "sk-test", fetch: script.fetch });

  return {
    async generate_object() {
      script.answer(
        CHAT,
        json(completion({ role: "assistant", content: '{"city":"Paris","country":"France"}' })),
      );
      await ai.generateObject({
        model: openai.chat("gpt-4o-mini"),
        prompt: "Capital of France, as JSON.",
        schema: ai.jsonSchema({
          type: "object",
          properties: { city: { type: "string" }, country: { type: "string" } },
          required: ["city", "country"],
          additionalProperties: false,
        }),
        maxRetries: 0,
        ...telemetry,
      });
    },
  };
}

const DECISIONS = "https://api.openai.com/v1/decisions";
const SPEECH = "https://api.openai.com/v1/audio/speech";
const TRANSCRIPTIONS = "https://api.openai.com/v1/audio/transcriptions";

/**
 * A WebSocket for OpenAI's realtime transcription, scripted like the fetch:
 * it opens, takes the session update and the audio, and on the commit answers
 * with one transcript delta and the completed transcript. Nothing leaves the
 * process.
 */
class ScriptedTranscriptionSocket {
  constructor() {
    this.readyState = 0;
    this.bufferedAmount = 0;
    setImmediate(() => {
      this.readyState = 1;
      this.onopen?.();
    });
  }

  send(data) {
    if (JSON.parse(data).type !== "input_audio_buffer.commit") return;
    const message = (body) => this.onmessage?.({ data: JSON.stringify(body) });
    setImmediate(() => {
      message({ type: "conversation.item.input_audio_transcription.delta", item_id: "item_rec1", delta: "Paris is" });
      message({
        type: "conversation.item.input_audio_transcription.completed",
        item_id: "item_rec1",
        transcript: "Paris is the capital of France.",
      });
    });
  }

  close() {
    this.readyState = 3;
  }
}

/**
 * The calls only v7 traces through @ai-sdk/otel beyond text, objects and
 * embeddings: the experimental decide, speech, and transcription (one-shot and
 * streamed). Recorded by ./vercel-ai-otel only, after its other scenarios, so
 * those stay byte-identical.
 */
export function vercelDecideAudioScenarios({ ai, createOpenAI, script, telemetry }) {
  const openai = createOpenAI({ apiKey: "sk-test", fetch: script.fetch, webSocket: ScriptedTranscriptionSocket });

  return {
    async decide() {
      script.answer(
        DECISIONS,
        json({
          model: "gpt-6-luna",
          usage: { input_tokens: 30, output_tokens: 2, total_tokens: 32 },
          answers: [{ type: "predicate", name: "resolved", probability: 0.875 }],
        }),
      );
      await ai.experimental_decide({
        model: openai.decisionModel("gpt-6-luna"),
        state: "Customer: thanks, the refund arrived.",
        questions: { resolved: { type: "boolean", instructions: "Was the customer's issue resolved?" } },
        maxRetries: 0,
        ...telemetry,
      });
    },

    async generate_speech() {
      script.answer(SPEECH, { status: 200, body: "scripted-mp3", headers: { "content-type": "audio/mpeg" } });
      await ai.generateSpeech({
        model: openai.speech("gpt-4o-mini-tts"),
        text: "Paris is the capital of France.",
        voice: "alloy",
        maxRetries: 0,
        ...telemetry,
      });
    },

    async transcribe() {
      script.answer(
        TRANSCRIPTIONS,
        json({
          text: "Paris is the capital of France.",
          language: "english",
          duration: 2.5,
          usage: {
            type: "tokens",
            input_tokens: 14,
            input_token_details: { text_tokens: 0, audio_tokens: 14 },
            output_tokens: 8,
            total_tokens: 22,
          },
        }),
      );
      await ai.transcribe({
        model: openai.transcription("gpt-4o-transcribe"),
        audio: new Uint8Array([0x49, 0x44, 0x33, 0x04, 0x00, 0x00, 0x00, 0x00]),
        maxRetries: 0,
        ...telemetry,
      });
    },

    async stream_transcribe() {
      const audio = new ReadableStream({
        start(controller) {
          controller.enqueue(new Uint8Array([0, 1, 2, 3]));
          controller.enqueue(new Uint8Array([4, 5, 6, 7]));
          controller.close();
        },
      });
      const result = ai.experimental_streamTranscribe({
        model: openai.transcription("gpt-realtime-whisper"),
        audio,
        inputAudioFormat: { type: "audio/pcm", rate: 24000 },
        ...telemetry,
      });
      for await (const _ of result.fullStream) {
        // drain
      }
    },
  };
}
