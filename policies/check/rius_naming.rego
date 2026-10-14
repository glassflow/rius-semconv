package after_resolution

import rego.v1

# OpenTelemetry's attribute naming rules, scoped to the keys we own. The shared
# naming_conventions pack cannot run on this registry: it also judges the
# third-party keys we model as normalizer inputs (ai.usage.promptTokens is the
# Vercel AI SDK's spelling, not ours to change), and it rejects the
# rius.request template next to the rius.request.tool_choice attribute, a pair
# we define on purpose.

# Lowercase, dot-separated segments, each snake_case: starts with a letter,
# single underscores between alphanumeric runs.
rius_name_pattern := `^[a-z][a-z0-9]*(_[a-z0-9]+)*(\.[a-z][a-z0-9]*(_[a-z0-9]+)*)+$`

rius_owned_key(attr) if startswith(attr.key, "rius.")
rius_owned_key(attr) if object.get(attr, ["annotations", "rius", "origin"], "") == "rius"

deny contains finding if {
	some attr in input.registry.attributes
	rius_owned_key(attr)
	not regex.match(rius_name_pattern, attr.key)
	finding := {
		"id": "rius_attribute_name_invalid",
		"context": {"attribute_key": attr.key},
		"message": sprintf(
			"Attribute '%s' breaks the naming rules: lowercase, dot-separated segments, each snake_case (letters, digits, single underscores, starting with a letter).",
			[attr.key],
		),
		"level": "violation",
	}
}
