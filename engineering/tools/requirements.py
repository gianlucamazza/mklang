"""Offline requirement validation and traceability. Canonical engineering tool v0.1.0."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique,
        parse_constant=invalid,
    )


def local_file(root, name):
    # No network, absolute paths, symlink escape or traversal in an untrusted registry.
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe reference: {name}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError(f"missing or escaping reference: {name}")
    return resolved


def validate(registries, schema):
    validator = Draft202012Validator(schema)
    Draft202012Validator.check_schema(schema)
    errors, records, ids = [], [], set()
    for root, document in registries:
        problems = sorted(validator.iter_errors(document), key=lambda e: str(e.path))
        errors.extend(f"{root}: {list(e.path)}: {e.message}" for e in problems)
        if problems:
            continue
        namespace = {
            "mklang": "MKL",
            "mklang-platform": "MKP",
            "mklang-engineering": "ENG",
        }[document["repository"]]
        for req in document["requirements"]:
            rid = req["id"]
            if rid in ids:
                errors.append(f"{rid}: duplicate ID")
            ids.add(rid)
            if not rid.startswith(f"{req['category']}-{namespace}-"):
                errors.append(f"{rid}: category/repository mismatch")
            refs = req["references"]
            for kind, links in refs.items():
                for link in links:
                    try:
                        path = local_file(root, link["path"])
                        if (
                            "contains" in link
                            and link["contains"] not in path.read_text()
                        ):
                            raise ValueError(f"locator not found: {link}")
                    except (ValueError, OSError, UnicodeError) as exc:
                        errors.append(f"{rid}/{kind}: {exc}")
            if req["lifecycle"] in ("implemented", "verified", "released"):
                for kind in ("implementation", "tests"):
                    if not refs[kind]:
                        errors.append(f"{rid}: {kind} required for {req['lifecycle']}")
            if (
                req["risk"] in ("high", "critical")
                and req["lifecycle"] not in ("proposed", "reviewed", "rejected")
                and not refs["adr"]
            ):
                errors.append(f"{rid}: high-risk requirements need an ADR")
            if req["lifecycle"] in ("verified", "released"):
                if not refs["evidence"]:
                    errors.append(f"{rid}: verification needs evidence")
                for ref in refs["evidence"]:
                    try:
                        receipt = read_json(local_file(root, ref["path"]))
                        if (
                            receipt.get("schema_version") != 1
                            or receipt.get("result") != "passed"
                            or rid not in receipt.get("requirements", [])
                            or not receipt.get("command")
                            or not receipt.get("revision")
                        ):
                            raise ValueError("invalid passing receipt")
                        subjects = receipt.get("subjects", {})
                        required = {
                            x["path"]
                            for k in ("implementation", "tests")
                            for x in refs[k]
                        }
                        if not required.issubset(subjects):
                            raise ValueError(
                                "receipt does not bind implementation and tests"
                            )
                        for name, digest in subjects.items():
                            actual = hashlib.sha256(
                                local_file(root, name).read_bytes()
                            ).hexdigest()
                            if actual != digest:
                                raise ValueError(f"stale evidence: {name}")
                    except (ValueError, OSError, TypeError, AttributeError) as exc:
                        errors.append(f"{rid}/evidence: {exc}")
            records.append(req)
    for req in records:
        for target in req["depends_on"]:
            if target not in ids:
                errors.append(f"{req['id']}: unknown requirement {target}")
    graph = {r["id"]: r["depends_on"] for r in records}
    active, done = set(), set()

    def visit(node):
        if node in active:
            errors.append(f"{node}: cyclic requirement dependency")
            return
        if node in done:
            return
        active.add(node)
        for target in graph.get(node, []):
            visit(target)
        active.remove(node)
        done.add(node)

    for node in graph:
        visit(node)
    rows = [
        {
            "id": r["id"],
            "lifecycle": r["lifecycle"],
            "risk": r["risk"],
            "verification": r["verification"]["kind"],
            **r["references"],
        }
        for r in sorted(records, key=lambda r: r["id"])
    ]
    return {
        "schema_version": 1,
        "valid": not errors,
        "errors": sorted(errors),
        "coverage": {
            "total": len(rows),
            **{
                k: sum(bool(row[k]) for row in rows)
                for k in ("implementation", "tests", "adr", "evidence")
            },
        },
        "requirements": rows,
    }


def markdown(report):
    lines = [
        "# Requirement traceability",
        "",
        "Generated mapping coverage; links do not prove behavior or model quality.",
        "",
        "| ID | Lifecycle | Risk | Verification | Implementation | Tests | ADR | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["requirements"]:
        values = [row[k] for k in ("id", "lifecycle", "risk", "verification")]
        values += [
            ", ".join(x["path"].replace("|", "\\|") for x in row[k]) or "—"
            for k in ("implementation", "tests", "adr", "evidence")
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", type=Path, nargs="+", help="repository roots")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "schemas/requirements-v1.schema.json",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        registries = [
            (root, read_json(root / "requirements/registry.json"))
            for root in args.roots
        ]
        report = validate(registries, read_json(args.schema))
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "valid": False,
                    "errors": [str(exc)],
                    "error_type": "input",
                }
            )
        )
        return 2
    print(
        markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    )
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
