# Opportunity research

Research date: 2026-09-10. The links below are primary documentation or issue
threads unless noted otherwise.

## Selected opportunity

GitHub's Dependabot documentation requires `.github/dependabot.yml` to contain
`version` and `updates`, and each update entry needs an ecosystem and directory.
The directory is repository-specific, and GitHub Actions has a special root
directory convention. Those rules make a local config-to-checkout map useful,
but the official documentation does not provide a local coverage report:

* [Dependabot configuration options](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-dependency-updates)
* [Dependabot configuration file reference](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-dependency-updates#dependabot-version-updates-configuration-options)

The need is visible in [dependabot-core issue #4605](https://github.com/dependabot/dependabot-core/issues/4605), which asks for a way to validate a Dependabot file before it lands on `main`. A real 2026 report, [issue #15681](https://github.com/dependabot/dependabot-core/issues/15681), shows a Docker entry targeting a stale/nonexistent directory and Dependabot failing to resolve the expected files. Monorepos add another failure mode: [issue #7750](https://github.com/dependabot/dependabot-core/issues/7750) documents directory/glob coverage and update-entry limits.

The adjacent user question [How can I test dependabot.yml before merging?](https://stackoverflow.com/questions/71217407/how-can-i-test-dependabot-yml-before-merging) records that the old validator/action stopped working and that generic schema hooks do not catch all repository or registry issues.

## Existing alternatives and why they are insufficient

| Candidate | Evidence | Decision |
| --- | --- | --- |
| Generic Dependabot schema hook | [`check-jsonschema`](https://github.com/python-jsonschema/check-jsonschema) has a mature vendored SchemaStore hook, `check-dependabot`, but validates structure rather than checkout coverage. | Complement, not a replacement. |
| npm validator | [`@bugron/validate-dependabot-yaml`](https://www.npmjs.com/package/@bugron/validate-dependabot-yaml) adds a few semantic checks, but is a small Node-only package with low adoption and no manifest scan. | Differentiate with offline Python distribution and coverage. |
| Full updater | [`dependabot/cli`](https://github.com/dependabot/cli) runs updater jobs in Docker. It is powerful but heavyweight for a pre-commit/CI doctor and still needs job setup. | Keep the local tool fast and dependency-light. |
| GitHub Actions/issue-form validation | [GitHub CLI issue #4031](https://github.com/cli/cli/issues/4031) requests local workflow and form validation; generic YAML/schema tools exist. | Broader space with less specific coverage value. |
| Documentation/code-block drift | Tools such as [`txm`](https://github.com/anko/txm) and [`mdcode`](https://github.com/szkiba/mdcode) already execute or lint Markdown snippets. | Saturated and not repository-config specific. |
| Path portability audit | Existing projects in this workspace and tools such as [`git-path-audit`](https://github.com/bunta-expert/git-path-audit) already target cross-platform filename hazards. | Avoid duplicate scope. |

## Why this deserves to exist

The job sits between schema linting and a full Dependabot run: it is fast,
offline, reviewable in a pull request, and explains exactly which local
manifest a configuration entry covers. That makes a common “green YAML, red
Dependabot” failure visible before merge while remaining useful to projects
that cannot grant a CI job registry or GitHub credentials.

## Risks and mitigations

* Dependabot supports many ecosystems and evolves. The supported ecosystem
  table is explicit, tests are fixture-driven, and unknown manifest types are
  reported as unknown instead of falsely unmanaged.
* Globs can be subtle. Paths are normalized and matching is deterministic; the
  report shows the concrete files matched by every entry.
* A local scanner cannot reproduce private registry access. Registry secrets
  are never read or printed, and documentation clearly labels the tool as a
  local ruleset rather than an updater replacement.
