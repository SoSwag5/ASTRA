"""Generate a CycloneDX 1.5 SBOM from installed Python metadata + npm lockfile.

Dependency-free (stdlib only) so it needs no extra packages in the venv. It records
what is actually installed/locked; it does NOT perform vulnerability analysis (see
scripts/audit_dependencies.py and the CI pip-audit / npm audit steps for that) and
does not prove any package is non-malicious.
"""
import importlib.metadata as md
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'security'
OUT.mkdir(exist_ok=True)


def purl(ecosystem, name, version):
    return f'pkg:{ecosystem}/{name}@{version}'


def python_components():
    comps = []
    for dist in sorted(md.distributions(), key=lambda d: (d.metadata['Name'] or '').lower()):
        name = dist.metadata['Name']
        if not name:
            continue
        version = dist.version
        lic = (dist.metadata.get('License-Expression') or dist.metadata.get('License')
               or '; '.join(c.split('::')[-1].strip() for c in dist.metadata.get_all('Classifier', [])
                            if c.startswith('License ::')) or 'UNKNOWN')
        comp = {'type': 'library', 'name': name, 'version': version,
                'purl': purl('pypi', name, version),
                'properties': [{'name': 'astra:ecosystem', 'value': 'PyPI'}]}
        if lic and lic != 'UNKNOWN':
            comp['licenses'] = [{'license': {'name': lic[:200]}}]
        comps.append(comp)
    return comps


def npm_components():
    lock = ROOT / 'frontend' / 'package-lock.json'
    if not lock.exists():
        return []
    data = json.loads(lock.read_text(encoding='utf-8'))
    comps = []
    for path, entry in data.get('packages', {}).items():
        if not path or 'version' not in entry:
            continue
        name = path.split('node_modules/')[-1]
        version = entry['version']
        comp = {'type': 'library', 'name': name, 'version': version,
                'purl': purl('npm', name, version),
                'properties': [{'name': 'astra:ecosystem', 'value': 'npm'},
                               {'name': 'astra:dev', 'value': str(entry.get('dev', False))}]}
        if entry.get('license'):
            comp['licenses'] = [{'license': {'name': str(entry['license'])[:200]}}]
        if entry.get('integrity'):
            algo, _, val = entry['integrity'].partition('-')
            comp['hashes'] = [{'alg': {'sha512': 'SHA-512', 'sha256': 'SHA-256', 'sha1': 'SHA-1'}.get(algo, algo), 'content': val}]
        comps.append(comp)
    return comps


def main():
    components = python_components() + npm_components()
    sbom = {
        'bomFormat': 'CycloneDX',
        'specVersion': '1.5',
        'serialNumber': f'urn:uuid:{uuid.uuid4()}',
        'version': 1,
        'metadata': {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'component': {'type': 'application', 'name': 'astra', 'version': '1.0.0'},
            'tools': [{'name': 'astra-generate-sbom', 'version': '1.0'}],
        },
        'components': components,
    }
    target = OUT / 'sbom.cdx.json'
    target.write_text(json.dumps(sbom, indent=2), encoding='utf-8')
    py = sum(1 for c in components if c['purl'].startswith('pkg:pypi'))
    npm = sum(1 for c in components if c['purl'].startswith('pkg:npm'))
    print(json.dumps({'written': str(target.relative_to(ROOT)), 'pypi': py, 'npm': npm, 'total': len(components)}))


if __name__ == '__main__':
    main()
