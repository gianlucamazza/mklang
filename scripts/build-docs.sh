#!/usr/bin/env bash
# Assemble the mkdocs source tree from the repo's canonical markdown files.
# The repo stays the single source of truth; site-src/ is generated and ignored.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf site-src
mkdir -p site-src/adr

cp README.md site-src/index.md
cp SPEC.md ROADMAP.md CHANGELOG.md CONTRIBUTING.md site-src/
cp docs/patterns.md site-src/
cp docs/authoring.md site-src/
cp docs/stdlib.md site-src/
cp conformance/README.md site-src/conformance.md
cp docs/adr/*.md site-src/adr/
cp -r schema site-src/schema

# Rewrite repo-relative links for the flattened site: in-site pages point to
# their new location; repo-only targets (examples, config, sources) go to GitHub.
#
# Match the *prefix* of the markdown target (open paren + path start) — never
# require the closing `)` immediately after a directory name, or longer paths
# like `(./docs/adr/0010-….md)` and `(./docs/experiments/…)` stay unrewritten
# and fail `mkdocs --strict`.
GH="https://github.com/gianlucamazza/mklang"
find site-src -maxdepth 2 -name '*.md' -print0 | xargs -0 sed -i \
	-e "s|(\./conformance/README\.md)|(conformance.md)|g" \
	-e "s|(\.\./conformance/README\.md)|(conformance.md)|g" \
	-e "s|(\.\./\.\./conformance/README\.md)|(../conformance.md)|g" \
	-e "s|(\./docs/patterns\.md)|(patterns.md)|g" \
	-e "s|(\.\./docs/patterns\.md)|(patterns.md)|g" \
	-e "s|(\.\./SPEC\.md)|(SPEC.md)|g" \
	-e "s|(\./docs/adr/\([^)]*\.md\))|(adr/\1)|g" \
	-e "s|(\./docs/adr)|($GH/tree/main/docs/adr)|g" \
	-e "s|(\./docs/|($GH/tree/main/docs/|g" \
	-e "s|(\./docs)|($GH/tree/main/docs)|g" \
	-e "s|(\./examples/|($GH/blob/main/examples/|g" \
	-e "s|(\.\./examples/|($GH/blob/main/examples/|g" \
	-e "s|(\.\./config/|($GH/blob/main/config/|g" \
	-e "s|(\./config/|($GH/blob/main/config/|g" \
	-e "s|(\./scripts/|($GH/blob/main/scripts/|g" \
	-e "s|(\.\./scripts/|($GH/blob/main/scripts/|g" \
	-e "s|(\./src/mklang)|($GH/tree/main/src/mklang)|g" \
	-e "s|(\./schema/|($GH/blob/main/schema/|g" \
	-e "s|(\.\./schema/|($GH/blob/main/schema/|g" \
	-e "s|(\./LICENSE)|($GH/blob/main/LICENSE)|g" \
	-e "s|(\.\./README\.md)|(index.md)|g" \
	-e "s|(\./ROADMAP\.md)|(ROADMAP.md)|g" \
	-e "s|(\./CHANGELOG\.md)|(CHANGELOG.md)|g" \
	-e "s|(\./CONTRIBUTING\.md)|(CONTRIBUTING.md)|g" \
	-e "s|(\./SPEC\.md)|(SPEC.md)|g"

echo "site-src assembled: $(find site-src -name '*.md' | wc -l) pages"
