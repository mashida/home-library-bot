import json
from pathlib import Path

BASE = Path('catalog')
INDEX_DIR = BASE / 'indices'
INDEX_DIR.mkdir(parents=True, exist_ok=True)

entity_dirs = [BASE / 'people', BASE / 'companies', BASE / 'tools', BASE / 'sources']

# Merge all JSONL files into main.jsonl
with open(INDEX_DIR / 'main.jsonl', 'w', encoding='utf-8') as main_out:
    for d in entity_dirs:
        for path in sorted(d.glob('*.jsonl')):
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        main_out.write(line if line.endswith('\n') else line + '\n')

# Merge summary counts
summary_files = sorted((INDEX_DIR).glob('summary__*_batch_1.json'))
summary_data = {}
for path in summary_files:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        summary_data[data['topic']] = data['counts']

total = {"PERSON": 0, "COMPANY": 0, "TOOL": 0, "SOURCE": 0}
for counts in summary_data.values():
    for k in total.keys():
        total[k] += counts.get(k, 0)

with open(INDEX_DIR / 'summary.json', 'w', encoding='utf-8') as f:
    json.dump({"topics": summary_data, "total": total}, f, indent=2)
