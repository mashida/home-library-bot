import json
from pathlib import Path
from jsonschema import validate, ValidationError

BASE = Path('catalog')
ENTITY_SCHEMA = json.load(open('schemas/entity.schema.json'))
SUMMARY_SCHEMA = json.load(open('schemas/summary.schema.json'))

errors = []

for d in ['people', 'companies', 'tools', 'sources']:
    for path in (BASE / d).glob('*.jsonl'):
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    validate(json.loads(line), ENTITY_SCHEMA)
                except ValidationError as e:
                    errors.append(f"{path}:{i}: {e.message}")

index_dir = BASE / 'indices'
for path in index_dir.glob('summary__*_batch_1.json'):
    with open(path, 'r', encoding='utf-8') as f:
        try:
            validate(json.load(f), SUMMARY_SCHEMA)
        except ValidationError as e:
            errors.append(f"{path}: {e.message}")

if errors:
    print('Validation errors:')
    for e in errors:
        print(' -', e)
    raise SystemExit(1)

print('All files validated successfully.')
