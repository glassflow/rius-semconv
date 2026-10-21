# Changelog

## [1.8.0](https://github.com/glassflow/rius-semconv/compare/v1.7.0...v1.8.0) (2026-10-21)


### Features

* register a compaction convention every producer can fill ([#78](https://github.com/glassflow/rius-semconv/issues/78)) ([6e538d5](https://github.com/glassflow/rius-semconv/commit/6e538d5f4713c9f3bf059f7425bd9b39cbf45ccd))

## [1.7.0](https://github.com/glassflow/rius-semconv/compare/v1.6.0...v1.7.0) (2026-10-21)


### Features

* decide pydantic-ai's Gemini image and audio usage details ([#83](https://github.com/glassflow/rius-semconv/issues/83)) ([e1c20a5](https://github.com/glassflow/rius-semconv/commit/e1c20a5b768865b711e7ef977e33dbe824d8ebc6))
* media parts contract and byte-identical raw-payload stripping ([#74](https://github.com/glassflow/rius-semconv/issues/74)) ([c57bca4](https://github.com/glassflow/rius-semconv/commit/c57bca42590b2986741859178b76660682295067))
* settle non-http URIs, empty and redacted references and the Vercel fallback in media parts ([#81](https://github.com/glassflow/rius-semconv/issues/81)) ([c41e782](https://github.com/glassflow/rius-semconv/commit/c41e782da010d95a1ca7ef241580b0bfdc58cbe6))
* strip LangChain v1, Bedrock and Mistral audio base64 from raw payloads ([#80](https://github.com/glassflow/rius-semconv/issues/80)) ([2ee2925](https://github.com/glassflow/rius-semconv/commit/2ee29256a0a38184f3495cf2f45028bc98bdb524))
* strip Vercel image parts and LangChain v0 base64, write byte objects as the strip marker, map LangChain v1 reference blocks ([#82](https://github.com/glassflow/rius-semconv/issues/82)) ([8436c52](https://github.com/glassflow/rius-semconv/commit/8436c523f40e67af0caf1c25bce5e8d24f1f3667))


### Bug Fixes

* strip a data URL that follows a link or wraps across lines ([#84](https://github.com/glassflow/rius-semconv/issues/84)) ([2be324c](https://github.com/glassflow/rius-semconv/commit/2be324c7a914e66de964e34e184c70305755f39f))

## [1.6.0](https://github.com/glassflow/rius-semconv/compare/v1.5.0...v1.6.0) (2026-10-19)


### Features

* generate the Python module without an OpenTelemetry import ([#70](https://github.com/glassflow/rius-semconv/issues/70)) ([491cb24](https://github.com/glassflow/rius-semconv/commit/491cb2438f36081d1782b76ca56955c50fbab4cf))
* register the coding-agent plugin's keys ([#69](https://github.com/glassflow/rius-semconv/issues/69)) ([ab1dccb](https://github.com/glassflow/rius-semconv/commit/ab1dccbde4e0d7cfd140836779a2c51fea8a92ce))

## [1.5.0](https://github.com/glassflow/rius-semconv/compare/v1.4.0...v1.5.0) (2026-10-16)


### Deprecations

* **deprecate:** deprecate mcp.result_type and gen_ai.first_token ([#63](https://github.com/glassflow/rius-semconv/issues/63)) ([b80499c](https://github.com/glassflow/rius-semconv/commit/b80499cc5a407b9f12a2f9e01195920db08cbc76))


### Bug Fixes

* expect time to first chunk, not a gen_ai.first_token event, from the normalizers ([#66](https://github.com/glassflow/rius-semconv/issues/66)) ([fd1382e](https://github.com/glassflow/rius-semconv/commit/fd1382e93b4762083bafe538d8976776298ac4f7))

## [1.4.0](https://github.com/glassflow/rius-semconv/compare/v1.3.0...v1.4.0) (2026-10-15)


### Features

* classify @ai-sdk/otel's decide, speech and transcription operations as LLM, and record them ([#59](https://github.com/glassflow/rius-semconv/issues/59)) ([9923175](https://github.com/glassflow/rius-semconv/commit/9923175d13b46dcf138ab44fbf83fa4785a37792))

## [1.3.0](https://github.com/glassflow/rius-semconv/compare/v1.2.0...v1.3.0) (2026-10-14)


### Deprecations

* **deprecate:** reference gen_ai.main_agent.{id,name,description} and deprecate rius.main_agent.{id,name,description} ([#42](https://github.com/glassflow/rius-semconv/issues/42)) ([6f4d9e8](https://github.com/glassflow/rius-semconv/commit/6f4d9e865f778218fa6937d56b54ea03f1810dea))


### Bug Fixes

* list stop first among the stop_sequences spellings, as both SDKs do ([#49](https://github.com/glassflow/rius-semconv/issues/49)) ([243195f](https://github.com/glassflow/rius-semconv/commit/243195f3927d32578d575cb9addfa6fa475c6ce0))

## [1.2.0](https://github.com/glassflow/rius-semconv/compare/v1.1.0...v1.2.0) (2026-10-14)


### Features

* reference upstream keys from the Weaver registry, and describe the normalizer inputs ([#40](https://github.com/glassflow/rius-semconv/issues/40)) ([504bd6f](https://github.com/glassflow/rius-semconv/commit/504bd6f3f4a77513e69a7d3fcc15b6808f40de30))
* write the rius.* attributes as a Weaver registry, with briefs, examples and stability ([#39](https://github.com/glassflow/rius-semconv/issues/39)) ([14c3159](https://github.com/glassflow/rius-semconv/commit/14c3159fb6653fd696da56ef21df77904992eab3))


### Bug Fixes

* model the pydantic_ai.cache prefix as a template Weaver can match ([#46](https://github.com/glassflow/rius-semconv/issues/46)) ([f1f1714](https://github.com/glassflow/rius-semconv/commit/f1f17145993ab523b5b0b755b2374fbc6ec704d0))

## [1.1.0](https://github.com/glassflow/rius-semconv/compare/v1.0.0...v1.1.0) (2026-10-13)


### Features

* add OpenInference's RERANKER span kind, and record the Vercel AI SDK v6 rerank call ([#25](https://github.com/glassflow/rius-semconv/issues/25)) ([c67d37d](https://github.com/glassflow/rius-semconv/commit/c67d37dbb1c6316afdad49bb48076399cef8a61d))
* record Vercel AI SDK v7 with the usage option, add generateObject, and classify agent_step as CHAIN ([#26](https://github.com/glassflow/rius-semconv/issues/26)) ([a87d1a0](https://github.com/glassflow/rius-semconv/commit/a87d1a07cc75acdf1a79900b6e89581955c40e49))

## 1.0.0 (2026-10-13)


### Features

* record Vercel AI SDK v6 and map the ai.* usage keys natively ([2a79809](https://github.com/glassflow/rius-semconv/commit/2a798096edfb07a2c93a033378a85b6f5b3da751))


### Bug Fixes

* leave v5's last-step generateText usage unread ([4890265](https://github.com/glassflow/rius-semconv/commit/4890265fa090ac85e978cf8db3d3e5ddba63b98c))
