# Changelog

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
