---
type: known-limitation
status: open
created: 2026-11-26
tags: [config, flows, breaking-change]
---

# Known limitation: Config requires flows

`flows` is required in `FactoryConfig`, a breaking change: a config without a `flows` section (e.g. an older `FACTORY_CONFIG` file) no longer loads. Its keys must be `FlowName` values (`factory/core/models.py`), and an unknown one also fails the load.

Add the section as in `factory/config.json`.
