# Catalog Data Contract

This repository stores structured information about people, companies, tools, and information sources.

## Deduplication
- **PERSON**: deduplicate by the combination of GitHub and Twitter handles.
- **COMPANY**: deduplicate by domain and organisation name.
- **TOOL**: deduplicate by canonical repository URL.
- **SOURCE**: deduplicate by RSS feed URL.

## Activity
An entity is considered active if it has released code, published content, or otherwise updated within the last 12 months. If inactive, set `is_active` to `false` and `last_content_at` to `null`.

## Fields
Entities follow `schemas/entity.schema.json`. Each record must specify:
- `update_channels`: list of URLs where updates appear (e.g. GitHub releases, blogs).
- `source_evidence`: URL pointing to evidence describing the entity.

## Storage
Data is stored as JSON Lines (`.jsonl`) under `catalog/`. Summary files live in `catalog/indices/`.
