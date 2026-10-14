package after_resolution

import rego.v1

# The registry is written for readers outside the team: a decision is recorded
# as its reason, never as an internal ticket number. Covers the strings we
# write in model/: each attribute defined here, each group's own fields and the
# rius annotation on its refs (a ref's brief and note are upstream's prose),
# and each event. tools/check_registry.py runs the same rule over registry/,
# including the files Weaver does not read.

rius_ticket_pattern := `\b(RIUS|GLA2?)-[0-9]+\b`

rius_prose contains [label, node] if {
	some attr in input.registry.attributes
	label := attr.key
	node := attr
}

rius_prose contains [label, node] if {
	some group in input.registry.attribute_groups
	label := group.id
	node := object.remove(group, ["attributes"])
}

rius_prose contains [label, node] if {
	some group in input.registry.attribute_groups
	some attr in group.attributes
	label := sprintf("%s ref %s", [group.id, attr.key])
	node := object.get(attr, ["annotations", "rius"], {})
}

rius_prose contains [label, node] if {
	some event in object.get(input.registry, "events", [])
	label := event.name
	node := object.remove(event, ["attributes"])
}

deny contains finding if {
	some [label, node] in rius_prose
	walk(node, [_, value])
	is_string(value)
	some ticket in regex.find_n(rius_ticket_pattern, value, -1)
	finding := {
		"id": "rius_ticket_id_in_prose",
		"context": {"location": label, "ticket": ticket},
		"message": sprintf(
			"%s mentions the ticket id %s. The registry is read outside the team: write the reason instead.",
			[label, ticket],
		),
		"level": "violation",
	}
}
