"""Validate CycloneDX 1.7 with maintained tooling and check graph integrity."""
import argparse
import hashlib
import json
from pathlib import Path
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator

def validate(path):
    raw = Path(path).read_bytes()
    bom = json.loads(raw)
    if bom.get('specVersion') != '1.7':
        raise ValueError('CycloneDX 1.7 required')
    errors = JsonStrictValidator(SchemaVersion.V1_7).validate_str(raw.decode())
    if errors:
        raise ValueError('CycloneDX schema validation failed: ' + str(errors))
    components = bom['components']
    refs = [c['bom-ref'] for c in components] + [bom['metadata']['component']['bom-ref']]
    if len(refs) != len(set(refs)):
        raise ValueError('Duplicate component identifiers')
    graph = bom.get('dependencies', [])
    if {d['ref'] for d in graph} != set(refs):
        raise ValueError('Incomplete dependency graph')
    for entry in graph:
        if not set(entry.get('dependsOn', [])) <= set(refs):
            raise ValueError('Unresolved dependency graph reference')
    if not {'pkg:pypi', 'pkg:npm'} <= {c.get('purl', '').split('/')[0] for c in components}:
        raise ValueError('Both Python and npm inventory required')
    return {'status': 'PASS', 'specification': '1.7', 'components': len(components), 'sha256': hashlib.sha256(raw).hexdigest()}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bom', type=Path)
    print(json.dumps(validate(parser.parse_args().bom)))
