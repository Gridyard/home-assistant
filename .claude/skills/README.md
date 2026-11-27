# Home Assistant skills

Unmodified copies of the agent skills from Home Assistant Core, commit
[`95a7910`](https://github.com/home-assistant/core/tree/95a79104144c03c3d6164374954d0e00337272d0/.claude/skills),
licensed under Apache-2.0 like this repository.

| Skill | Use |
| --- | --- |
| `ha-integration-knowledge` | primary reference when writing or testing the integration |
| `ha-quality-scale-verify` | check a quality scale rule or tier |
| `ha-review` | review changes before a pull request |

The skills use Core paths. In this repository `homeassistant/components/<domain>` is `custom_components/gridyard`,
and `tests/components/<domain>` is `tests`. To update, copy the folders from a newer Core commit and change the link
above.
