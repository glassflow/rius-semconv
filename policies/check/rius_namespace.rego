package after_resolution

import rego.v1

# Helpers are prefixed rius_: every file in the after_resolution package,
# the shared OTel packs included, shares one namespace.

# Whose keys this registry defines. Every attribute in input.registry.attributes
# is defined here (a ref into a dependency appears only inside its group), so
# each one is either ours, or a key another producer writes that a Rius
# normalizer reads (model/inputs/).

rius_annotation(attr) := object.get(attr, ["annotations", "rius"], {})

# Another producer's key: a normalizer input, or a key whose origin names
# another producer (the OpenInference keys the SDKs also write).
rius_third_party(attr) if rius_annotation(attr).normalizer_input
rius_third_party(attr) if rius_annotation(attr).producer

rius_third_party(attr) if {
	origin := rius_annotation(attr).origin
	not origin in {"rius", "otel"}
}

# Every key we define is under rius.*, unless its row says why not: a
# namespace_exception (a key that predates the rule), or a deprecation (a
# former spelling, kept so readers still recognise it). A key in an
# OpenTelemetry namespace gets the rule below instead.
deny contains finding if {
	some attr in input.registry.attributes
	not startswith(attr.key, "rius.")
	not rius_upstream_namespace(attr.key)
	not rius_third_party(attr)
	not rius_annotation(attr).origin == "otel"
	not rius_annotation(attr).namespace_exception
	not attr.deprecated
	finding := {
		"id": "rius_attribute_outside_namespace",
		"context": {"attribute_key": attr.key},
		"message": sprintf(
			"Attribute '%s' is not under rius.*. Name it rius.<...>, give its row a namespace_exception saying why not, or, if another producer writes it, model it in model/inputs/ as a normalizer input.",
			[attr.key],
		),
		"level": "violation",
	}
}

# An OpenTelemetry key is referenced from its pinned upstream registry, never
# defined here: a local copy would drift from upstream silently.
deny contains finding if {
	some attr in input.registry.attributes
	rius_upstream_namespace(attr.key)
	finding := {
		"id": "rius_upstream_namespace_defined",
		"context": {"attribute_key": attr.key},
		"message": sprintf(
			"Attribute '%s' is in a namespace OpenTelemetry owns, so it must be a ref to the upstream definition (group rius.upstream), not defined here.",
			[attr.key],
		),
		"level": "violation",
	}
}

deny contains finding if {
	some attr in input.registry.attributes
	not rius_upstream_namespace(attr.key)
	rius_annotation(attr).origin == "otel"
	finding := {
		"id": "rius_upstream_namespace_defined",
		"context": {"attribute_key": attr.key},
		"message": sprintf(
			"Attribute '%s' is an OpenTelemetry key (origin otel), so it must be a ref to the upstream definition (group rius.upstream), not defined here.",
			[attr.key],
		),
		"level": "violation",
	}
}

rius_upstream_namespace(key) if startswith(key, "gen_ai.")
rius_upstream_namespace(key) if startswith(key, "otel.")

# Every attribute defined here carries the rius annotation the generators read.
deny contains finding if {
	some attr in input.registry.attributes
	not attr.annotations.rius
	finding := {
		"id": "rius_annotation_missing",
		"context": {"attribute_key": attr.key},
		"message": sprintf(
			"Attribute '%s' has no `rius` annotation. Write its row in registry/ and rerun tools/to_weaver.py, which adds it.",
			[attr.key],
		),
		"level": "violation",
	}
}
