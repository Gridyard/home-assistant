# AGENTS.md

Home Assistant custom integration `gridyard`, installed through HACS. This repository is public.

| Path | Content |
| --- | --- |
| `custom_components/gridyard/` | the integration |
| `tests/` | tests with `pytest-homeassistant-custom-component` |
| `.claude/skills/` | Home Assistant Core agent skills ([README](.claude/skills/README.md)) |

## Rules

- Use `ha-integration-knowledge` when writing or testing and `ha-review` before every pull request.
- Protocol and device logic belong in the library [`gridyard`](https://github.com/Gridyard/python-gridyard), not in
  the integration.
- Tests run against the Home Assistant version that `pytest-homeassistant-custom-component` in
  `requirements_test.txt` pins.
- Nothing internal: no server addresses, real device IDs, setup codes, keys, readings or local paths. Test data is
  synthetic. Code, commits and documentation are in English.
- Pin dependencies; pin GitHub Actions to a commit SHA with the version as a comment.
- Work on `stage/<task>` branches with Conventional Commits and open a pull request to `main`. Only maintainers merge.
- Before a pull request run `ruff check`, `ruff format --check` and `pytest`. CI also runs hassfest and HACS.
