"""Compare the verified CycloneDX predicate to the independently validated BOM.

Input is gh attestation verify --format json output, never an unverified bundle.
The workflow must first require a successful cryptographic verification exit.
"""
import json
import sys
from pathlib import Path

def matches(bom, verification):
    if isinstance(verification, dict):
        if verification.get('predicateType') == 'https://cyclonedx.org/bom' and verification.get('predicate') == bom:
            return True
        return any(matches(bom, v) for v in verification.values())
    if isinstance(verification, list):
        return any(matches(bom, v) for v in verification)
    return False

if __name__ == '__main__':
    bom = json.loads(Path(sys.argv[1]).read_text())
    verification = json.loads(Path(sys.argv[2]).read_text())
    if not matches(bom, verification):
        raise SystemExit('Verified SBOM predicate does not match the validated release SBOM')
    print('Verified attestation predicate matches the validated SBOM')
