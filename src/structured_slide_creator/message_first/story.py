"""Message-first prose, concepts and evidence; independent of legacy DeckPlan."""

from .common import (
    PlanIssue,
    identifiers,
    read_document,
    records,
    required_text,
    string,
    strings,
)


def load_story(path):
    doc = read_document(path)
    check_story_types(doc.data)
    return doc


def check_story_types(data):
    for key in ("message", "audience", "purpose"):
        if key in data:
            string(data[key], key)
    for key in ("concepts", "assets", "sections"):
        records(data.get(key, []), key)
    fields = {
        "concepts": ("id", "label", "definition"),
        "assets": ("id", "path", "source", "role"),
        "sections": ("id", "claim", "body", "role"),
    }
    for kind, keys in fields.items():
        for index, item in enumerate(data.get(kind, [])):
            for key in keys:
                if key in item:
                    string(item[key], f"{kind}[{index}].{key}")
            if kind == "sections":
                for key in ("depends_on", "introduces", "uses", "evidence"):
                    if key in item:
                        strings(item[key], f"sections[{index}].{key}")


def validate_story(doc):
    data = doc.data
    check_story_types(data)
    issues = []
    required_text(data, ["message"], "story", issues)
    sections = data.get("sections", [])
    if not sections:
        issues.append(
            PlanIssue("error", "sections", "at least one section is required")
        )
    concepts = identifiers(data.get("concepts", []), "concepts", issues)
    assets = identifiers(data.get("assets", []), "assets", issues)
    section_ids = identifiers(sections, "sections", issues)
    for i, item in enumerate(data.get("concepts", [])):
        required_text(item, ["label", "definition"], f"concepts[{i}]", issues)
    prior_sections, introduced = set(), set()
    for i, section in enumerate(sections):
        where = f"sections[{i}] ({section.get('id', '')})"
        required_text(section, ["claim", "body"], where, issues)
        for key, known in [
            ("depends_on", section_ids),
            ("introduces", concepts),
            ("uses", concepts),
            ("evidence", assets),
        ]:
            values = section.get(key, [])
            if len(values) != len(set(values)):
                issues.append(PlanIssue("error", where, f"duplicate {key} reference"))
            for ref in values:
                if ref not in known:
                    issues.append(
                        PlanIssue("error", where, f"unknown {key} reference {ref!r}")
                    )
        for ref in section.get("depends_on", []):
            if ref in section_ids and ref not in prior_sections:
                issues.append(
                    PlanIssue(
                        "error", where, f"dependency {ref!r} must be an earlier section"
                    )
                )
        for ref in section.get("uses", []):
            if ref in concepts and ref not in introduced:
                issues.append(
                    PlanIssue(
                        "error",
                        where,
                        f"concept {ref!r} must be introduced in an earlier section",
                    )
                )
        for ref in section.get("introduces", []):
            if ref in introduced:
                issues.append(
                    PlanIssue(
                        "error", where, f"concept {ref!r} is introduced more than once"
                    )
                )
        introduced.update(section.get("introduces", []))
        prior_sections.add(section.get("id"))
    return issues


def story_to_markdown(doc):
    data = doc.data
    lines = ["# Central message", "", data.get("message", ""), ""]
    for key in ("audience", "purpose"):
        if data.get(key):
            lines += [f"**{key}**: {data[key]}", ""]
    concepts = {c["id"]: c for c in data.get("concepts", []) if "id" in c}
    assets = {a["id"]: a for a in data.get("assets", []) if "id" in a}
    for index, section in enumerate(data.get("sections", []), 1):
        lines += [
            f"## {index}. {section.get('id', '')} — {section.get('role', 'section')}",
            "",
            f"**Claim:** {section.get('claim', '')}",
            "",
            section.get("body", ""),
            "",
        ]
        if section.get("depends_on"):
            lines += [
                "**Requires earlier sections:** " + ", ".join(section["depends_on"]),
                "",
            ]
        for key in ("introduces", "uses"):
            for ref in section.get(key, []):
                c = concepts.get(ref, {})
                lines += [
                    f"- **{key} {ref} ({c.get('label', '')}):** {c.get('definition', '')}"
                ]
        for ref in section.get("evidence", []):
            a = assets.get(ref, {})
            details = [a.get("role", ""), a.get("source", "")]
            if a.get("path"):
                details.append(str(doc.resolve(a["path"])))
            lines += [f"- **evidence {ref}:** " + " / ".join(d for d in details if d)]
        lines.append("")
    return "\n".join(lines)
