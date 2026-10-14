package comparison_after_resolution

import rego.v1

# The compatibility rules in CONTRIBUTING.md ("Deprecation and compatibility")
# that the shared backwards-compatibility pack does not cover. input is this
# registry; data is the baseline, the last release. The shared pack already
# fails a removed attribute and a retyped stable one. Rows marked
# `status: planned` never shipped, so they may change freely.

rius_planned(attr) if object.get(attr, ["annotations", "rius", "status"], "") == "planned"

# The type on the wire: an enum is its members' value type, so adding a member
# or turning a string enum into a string is not a retype.
rius_wire_type(attr) := attr.type if is_string(attr.type)

rius_wire_type(attr) := "string" if {
	is_object(attr.type)
	every m in attr.type.members { is_string(m.value) }
}

rius_wire_type(attr) := "int" if {
	is_object(attr.type)
	every m in attr.type.members { is_number(m.value); m.value == floor(m.value) }
}

rius_wire_type(attr) := "double" if {
	is_object(attr.type)
	every m in attr.type.members { is_number(m.value) }
	some m in attr.type.members
	m.value != floor(m.value)
}

# Rule 5: a development key's type may not change. A new type is a new key,
# and the old one is deprecated.
deny contains finding if {
	some old in data.registry.attributes
	old.stability != "stable"
	not rius_planned(old)
	some new in input.registry.attributes
	new.key == old.key
	before := rius_wire_type(old)
	after := rius_wire_type(new)
	before != after
	finding := {
		"id": "rius_development_attribute_retyped",
		"context": {"attribute_key": old.key, "attribute_type": after, "previous_attribute_type": before},
		"message": sprintf(
			"Attribute '%s' was '%s' and is now '%s'. A shipped key keeps its type: add a new key with the new type and deprecate this one.",
			[old.key, before, after],
		),
		"level": "violation",
	}
}

# Rule 1 for the keys we reference rather than define: an upstream key we
# shipped a constant for stays referenced (deprecated if need be). The shared
# pack checks only the attributes a registry defines, and group membership only
# for stable groups.
rius_current_keys contains attr.key if {
	some attr in input.registry.attributes
}

rius_current_keys contains attr.key if {
	some group in input.registry.attribute_groups
	some attr in group.attributes
}

rius_baseline_defined contains attr.key if {
	some attr in data.registry.attributes
}

deny contains finding if {
	some group in data.registry.attribute_groups
	some attr in group.attributes
	not rius_baseline_defined[attr.key]
	not rius_planned(attr)
	not rius_current_keys[attr.key]
	finding := {
		"id": "rius_referenced_attribute_removed",
		"context": {"attribute_key": attr.key, "attribute_group_id": group.id},
		"message": sprintf(
			"Attribute '%s' was referenced in '%s' in the last release and no longer is. A shipped key is never removed: keep the ref and mark its row deprecated.",
			[attr.key, group.id],
		),
		"level": "violation",
	}
}
