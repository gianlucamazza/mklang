#!/usr/bin/env bash
# Assemble the mkdocs source tree from the repo's canonical markdown files.
# The repo stays the single source of truth; site-src/ is generated and ignored.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf site-src
mkdir -p site-src/adr site-src/experiments

cp README.md site-src/index.md
cp SPEC.md ROADMAP.md CHANGELOG.md CONTRIBUTING.md site-src/
# guides/ and reference/ are flattened to the site root so published URLs
# (/best-practices/, /stdlib/, ...) stay stable across the repo reorg.
cp docs/guides/*.md site-src/
cp docs/reference/*.md site-src/
cp docs/demos.md site-src/
cp conformance/README.md site-src/conformance.md
cp docs/adr/*.md site-src/adr/
cp docs/experiments/*.md site-src/experiments/
cp -r schema site-src/schema
cp -r docs/assets site-src/assets

# Rewrite repo-relative links for the flattened site: in-site pages point to
# their new location; repo-only targets (examples, config, sources) go to GitHub.
#
# A page's links are repo-relative from its *source* location; each pass below
# maps them to that page's *site* location, so the same source pattern can get
# a different rewrite per destination directory (root vs adr/ vs experiments/).
#
# Match the *prefix* of the markdown target (open paren + path start) — never
# require the closing `)` immediately after a file or directory name, or longer
# paths and `#anchor` suffixes stay unrewritten and fail `mkdocs --strict`.
# Depth-2 rules (../../) must precede their depth-1 (../) counterparts.
GH="https://github.com/gianlucamazza/mklang"

# Pass 1 — pages flattened to the site root. Sources sit at repo depth 0
# (README, SPEC, ...), depth 1 (conformance/README.md, docs/demos.md), and
# depth 2 (docs/guides/*, docs/reference/*); all their root-doc prefixes
# (./ , ../ , ../../) denote the repo root.
find site-src -maxdepth 1 -name '*.md' -print0 | xargs -0 sed -i \
	-e "s|(\./conformance/README\.md)|(conformance.md)|g" \
	-e "s|(\.\./\.\./conformance/README\.md)|(conformance.md)|g" \
	-e "s|(\.\./conformance/README\.md)|(conformance.md)|g" \
	-e "s|(\./docs/guides/|(|g" \
	-e "s|(\./docs/reference/|(|g" \
	-e "s|(\.\./guides/|(|g" \
	-e "s|(\.\./reference/|(|g" \
	-e "s|(\./docs/patterns\.md)|(patterns.md)|g" \
	-e "s|(\./docs/demos\.md|(demos.md|g" \
	-e "s|(\./docs/experiments/|(experiments/|g" \
	-e "s|(\./docs/assets/|(assets/|g" \
	-e "s|(\.\./assets/|(assets/|g" \
	-e 's|src="assets/demos/|src="../assets/demos/|g' \
	-e "s|(\.\./\.\./SPEC\.md|(SPEC.md|g" \
	-e "s|(\.\./SPEC\.md|(SPEC.md|g" \
	-e "s|(\./docs/adr/\([^)]*\.md\))|(adr/\1)|g" \
	-e "s|(\.\./adr/|(adr/|g" \
	-e "s|(\./docs/adr)|($GH/tree/main/docs/adr)|g" \
	-e "s|(\./docs/|($GH/tree/main/docs/|g" \
	-e "s|(\./docs)|($GH/tree/main/docs)|g" \
	-e "s|(\./examples/|($GH/blob/main/examples/|g" \
	-e "s|(\.\./\.\./examples/|($GH/blob/main/examples/|g" \
	-e "s|(\.\./examples/|($GH/blob/main/examples/|g" \
	-e "s|(\.\./\.\./config/|($GH/blob/main/config/|g" \
	-e "s|(\.\./config/|($GH/blob/main/config/|g" \
	-e "s|(\./config/|($GH/blob/main/config/|g" \
	-e "s|(\./scripts/|($GH/blob/main/scripts/|g" \
	-e "s|(\.\./\.\./scripts/|($GH/blob/main/scripts/|g" \
	-e "s|(\.\./scripts/|($GH/blob/main/scripts/|g" \
	-e "s|(\./src/mklang/|($GH/blob/main/src/mklang/|g" \
	-e "s|(\./src/mklang)|($GH/tree/main/src/mklang)|g" \
	-e "s|(\./schema/|($GH/blob/main/schema/|g" \
	-e "s|(\.\./\.\./schema/|($GH/blob/main/schema/|g" \
	-e "s|(\.\./schema/|($GH/blob/main/schema/|g" \
	-e "s|(\./LICENSE)|($GH/blob/main/LICENSE)|g" \
	-e "s|(\.\./README\.md)|(index.md)|g" \
	-e "s|(\.\./\.\./ROADMAP\.md|(ROADMAP.md|g" \
	-e "s|(\./ROADMAP\.md)|(ROADMAP.md)|g" \
	-e "s|(\.\./ROADMAP\.md)|(ROADMAP.md)|g" \
	-e "s|(\./CHANGELOG\.md)|(CHANGELOG.md)|g" \
	-e "s|(\.\./CHANGELOG\.md)|(CHANGELOG.md)|g" \
	-e "s|(\./CONTRIBUTING\.md)|(CONTRIBUTING.md)|g" \
	-e "s|(\.\./CONTRIBUTING\.md)|(CONTRIBUTING.md)|g" \
	-e "s|(\./SPEC\.md|(SPEC.md|g"

# Pass 2 — ADR pages stay under adr/; guide/reference targets sit one level up.
find site-src/adr -name '*.md' -print0 | xargs -0 sed -i \
	-e "s|(\.\./guides/|(../|g" \
	-e "s|(\.\./reference/|(../|g" \
	-e "s|(\.\./\.\./conformance/README\.md)|(../conformance.md)|g" \
	-e "s|(\.\./\.\./SPEC\.md|(../SPEC.md|g" \
	-e "s|(\.\./\.\./examples/|($GH/blob/main/examples/|g" \
	-e "s|(\.\./\.\./scripts/|($GH/blob/main/scripts/|g" \
	-e "s|(\.\./\.\./src/mklang/|($GH/blob/main/src/mklang/|g"

# Pass 3 — experiments pages: their only repo links point at scripts.
find site-src/experiments -name '*.md' -print0 | xargs -0 sed -i \
	-e "s|(\.\./\.\./scripts/|($GH/blob/main/scripts/|g"

test -f site-src/adr/README.md

# Raw HTML is opaque to MkDocs' link rewriting. These checks keep nested
# pretty URLs such as /demos/ from silently resolving media below /demos/assets/.
grep -q 'src="../assets/demos/cli.webm"' site-src/demos.md
grep -q 'src="../assets/demos/console.webm"' site-src/demos.md
grep -q 'src="../assets/demos/agent.webm"' site-src/demos.md
grep -q 'src="../assets/demos/hitl.webm"' site-src/demos.md
grep -q 'src="../assets/demos/search.webm"' site-src/demos.md
grep -q 'src="../assets/demos/test.webm"' site-src/demos.md

echo "site-src assembled: $(find site-src -name '*.md' | wc -l) pages"
