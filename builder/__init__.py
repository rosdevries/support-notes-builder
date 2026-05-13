"""Support Notes email builder package.

Mirrors the architecture of `expert-series-webinar-invite-builder`:

    .eml request   ─► eml_parser ─► (Claude Haiku) ─► SupportNotesData
                                                          │
                                                          ▼
                                                    slot_renderer
                                                          │
                                                          ▼
                                                     sfmc_client
                                                  (asset + image upload)

The package is multi-language: Korean is implemented first, with EN/JP/zh-CN/zh-TW
following the same pattern.  Per-language settings live in `language_config.py`.
"""
