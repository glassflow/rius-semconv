# Policies

Rego policies `weaver registry check` runs on the Weaver registry under
`model/`. `tools/weaver_check.py` runs them, together with two shared packs
from [opentelemetry-weaver-packages](https://github.com/open-telemetry/opentelemetry-weaver-packages)
at the commit `versions.env` pins (`WEAVER_PACKAGES_REF`), as they are:
`stability` and `backwards-compatibility`.

| File | Finding | What fails |
| --- | --- | --- |
| `check/rius_namespace.rego` | `rius_attribute_outside_namespace` | A key we define outside `rius.*`, with no `namespace_exception` and no deprecation. Other producers' keys (normalizer inputs, and keys whose `origin` names another producer) are exempt. |
| | `rius_upstream_namespace_defined` | A `gen_ai.*` or `otel.*` key, or any `origin: otel` key, defined here instead of referenced from upstream. |
| | `rius_annotation_missing` | An attribute with no `rius` annotation. |
| `check/rius_naming.rego` | `rius_attribute_name_invalid` | A key we own that is not lowercase, dot-separated, snake_case segments. |
| `check/rius_prose.rego` | `rius_ticket_id_in_prose` | An internal ticket id in the prose or annotations we write. |
| `check/rius_compat.rego` | `rius_development_attribute_retyped` | Against the baseline: a development attribute whose wire type changed. |
| | `rius_referenced_attribute_removed` | Against the baseline: an upstream key we referenced and no longer do. |

The shared `naming_conventions` pack does not run: it would also judge the
third-party keys we model (`ai.usage.promptTokens` is the Vercel AI SDK's
spelling), and it rejects the `rius.request` template next to the
`rius.request.tool_choice` attribute. `rius_naming.rego` applies its naming
rules to our own keys only.

`tools/check_registry.py` keeps the rules that need files Weaver does not
read (the params sidecar: allowlists, taxonomy, model parameters), and runs
the ticket-id rule over all of `registry/`.

## Tests

Each directory under `tests/` is a case: `current/` is the registry checked,
`base/` (when present) the baseline, and `expected.yaml` lists every finding
the case must produce, by id and attribute key (or location). A case loads
only `check/`. `tests/test_policies.py` runs them, and also runs the real
`model/` against itself as the baseline with one breaking change of each kind
applied, with the shared packs loaded:

```
export PATH="$PWD/.weaver/bin:$PATH"     # tools/install_weaver.sh
python -m pytest tests/test_policies.py
```
