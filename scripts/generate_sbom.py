"""CycloneDX 1.7: cyclonedx-py product inventory plus npm's exact lock graph.

Run in the separate assurance environment; --python selects the hash-installed
product environment. Includes build/optional packages; not JS bundle reachability.
"""
import argparse
import base64
import importlib.metadata as md
import json
import re
import subprocess
import sys
import tempfile
import tarfile
import io
import urllib.request
import hashlib
from pathlib import Path
from packageurl import PackageURL
from validate_sbom import validate

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.0-rc.1'

def normalize(name):
    return re.sub(r'[-_.]+', '-', name).lower()

def assemble(python):
    with tempfile.TemporaryDirectory(prefix='astra-bom-') as temp:
        target = Path(temp)/'python.json'
        subprocess.run([sys.executable, '-m', 'cyclonedx_py', 'environment', str(python),
                        '--sv', '1.7', '--output-reproducible', '-o', str(target)], check=True)
        bom = json.loads(target.read_text())
    pins = {normalize(n): v for n, v in re.findall(r'^([\w.-]+)==([\w.+-]+)', (ROOT/'requirements.lock.txt').read_text(), re.M)}
    selected = [c for c in bom['components'] if normalize(c['name']) in pins]
    if {normalize(c['name']): c['version'] for c in selected} != pins:
        raise ValueError('Product environment does not exactly match the complete Windows lock')
    allowed = {'type', 'name', 'version', 'purl', 'bom-ref', 'licenses', 'description'}
    components = [{k: v for k, v in c.items() if k in allowed} for c in selected]
    refmap = {c['bom-ref']: PackageURL(type='pypi', name=normalize(c['name']), version=c['version']).to_string() for c in components}
    graph = {}
    for c in components:
        c['bom-ref'] = refmap[c['bom-ref']]
        c['purl'] = c['bom-ref']
        c['properties'] = [{'name': 'astra:dependency-context', 'value': 'installed-by-setup; runtime-and-test-lock'}]
        graph[c['bom-ref']] = set()
    for d in bom.get('dependencies', []):
        if d['ref'] in refmap:
            graph[refmap[d['ref']]].update(refmap[r] for r in d.get('dependsOn', []) if r in refmap)
    npm = json.loads((ROOT/'frontend/package-lock.json').read_text())['packages']
    # Lockfiles omit versions of tarball-bundled dependencies. Read their package
    # manifests from integrity-verified registry archives; never extract or execute.
    for parent, entry in list(npm.items()):
        if not entry.get('bundleDependencies'):
            continue
        url = entry['resolved']
        if not url.startswith('https://registry.npmjs.org/'):
            raise ValueError('Bundled metadata must come from the npm registry')
        with urllib.request.urlopen(url, timeout=60) as response:
            archive = response.read(100_000_001)
        if len(archive) > 100_000_000:
            raise ValueError('Bundled package archive too large')
        alg, digest = entry['integrity'].split('-', 1)
        if hashlib.new(alg, archive).digest() != base64.b64decode(digest, validate=True):
            raise ValueError('Bundled archive integrity mismatch')
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            for member in tar:
                if not member.isfile() or not member.name.startswith('package/node_modules/') or not member.name.endswith('/package.json'):
                    continue
                if member.size > 1_000_000:
                    raise ValueError('Bundled package manifest too large')
                body = json.load(tar.extractfile(member))
                if not body.get('name') or not body.get('version'):
                    continue
                relative = member.name.removeprefix('package/').removesuffix('/package.json')
                if '/node_modules/' in relative or relative.startswith('node_modules/'):
                    npm[parent+'/'+relative] = {k: body[k] for k in ('name', 'version', 'license', 'dependencies', 'optionalDependencies', 'peerDependencies', 'peerDependenciesMeta') if k in body}
                    npm[parent+'/'+relative].update(dev=entry.get('dev', False), optional=entry.get('optional', False))
    pathrefs = {}
    byref = {c['bom-ref']: c for c in components}
    for path, entry in npm.items():
        if not path:
            continue
        name = entry.get('name') or path.rsplit('node_modules/', 1)[-1]
        namespace, _, short = name.rpartition('/')
        ref = PackageURL(type='npm', namespace=namespace or None, name=short, version=entry['version']).to_string()
        pathrefs[path] = ref
        context = 'build' if entry.get('dev') else 'frontend-runtime'
        c = {'type': 'library', 'name': name, 'version': entry['version'], 'bom-ref': ref, 'purl': ref,
             'properties': [{'name': 'astra:dependency-context', 'value': context},
                            {'name': 'astra:optional', 'value': str(bool(entry.get('optional'))).lower()}]}
        if entry.get('license'):
            c['licenses'] = [{'license': {'name': entry['license']}}]
        if entry.get('integrity'):
            c['hashes'] = []
            for sri in entry['integrity'].split():
                alg, encoded = sri.split('-', 1)
                if alg in ('sha512', 'sha256', 'sha1'):
                    c['hashes'].append({'alg': {'sha512': 'SHA-512', 'sha256': 'SHA-256', 'sha1': 'SHA-1'}[alg],
                                        'content': base64.b64decode(encoded, validate=True).hex()})
        if ref in byref:
            if context == 'frontend-runtime':
                byref[ref]['properties'][0]['value'] = context
            if byref[ref].get('hashes') != c.get('hashes'):
                raise ValueError('Conflicting npm integrity for identical package version')
        else:
            byref[ref] = c
        graph.setdefault(ref, set())

    def resolve(path, name):
        while True:
            candidate = (path+'/' if path else '')+'node_modules/'+name
            if candidate in pathrefs:
                return pathrefs[candidate]
            if not path:
                return None
            path = path.rsplit('/node_modules/', 1)[0] if '/node_modules/' in path else ''

    rootref = 'astra@'+VERSION
    direct = {normalize(n) for n in re.findall(r'^([\w.-]+)', (ROOT/'requirements.txt').read_text(), re.M)}
    graph[rootref] = {c['bom-ref'] for c in components if normalize(c['name']) in direct}
    for path, entry in npm.items():
        dependencies = {**entry.get('dependencies', {}), **entry.get('optionalDependencies', {}), **entry.get('peerDependencies', {})}
        if not path:
            dependencies.update(entry.get('devDependencies', {}))
        for name in dependencies:
            child = resolve(path, name)
            optional = name in entry.get('optionalDependencies', {}) or entry.get('peerDependenciesMeta', {}).get(name, {}).get('optional')
            if child is None and not optional:
                raise ValueError('Missing required npm dependency: '+name)
            if child:
                graph[pathrefs[path] if path else rootref].add(child)
    return {'$schema': 'http://cyclonedx.org/schema/bom-1.7.schema.json', 'bomFormat': 'CycloneDX', 'specVersion': '1.7', 'version': 1,
            'metadata': {'component': {'type': 'application', 'name': 'ASTRA', 'version': VERSION, 'bom-ref': rootref},
                         'tools': {'components': [{'type': 'application', 'name': n, 'version': md.version(n)} for n in ('cyclonedx-bom', 'cyclonedx-python-lib')]},
                         'properties': [{'name': 'astra:scope', 'value': 'Windows Python install and full npm lock; includes build and optional platform packages; OS, interpreters and optional downloaded browsers excluded'}]},
            'components': sorted(byref.values(), key=lambda c: c['bom-ref']),
            'dependencies': [{'ref': r, 'dependsOn': sorted(ds)} for r, ds in sorted(graph.items())]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'release'/('astra-'+VERSION+'.cdx.json'))
    args = parser.parse_args()
    bom = assemble(args.python.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bom, indent=2)+'\n', encoding='utf-8')
    evidence = validate(args.output)
    evidence.update(generator='cyclonedx-bom '+md.version('cyclonedx-bom')+' + ASTRA npm-lock graph adapter',
                    validator='cyclonedx-python-lib '+md.version('cyclonedx-python-lib'))
    args.output.with_suffix('.validation.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence))

if __name__ == '__main__':
    main()
