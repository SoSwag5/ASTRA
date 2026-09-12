"""Report only file paths and finding categories, never possible secret values."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
patterns={
 'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
 'api_token':rb'(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})',
 'literal_credential':rb'(?i)(?:api_key|password|app_token|secret)\s*[=:]\s*[\x22\x27]([^\x22\x27\r\n]{16,})[\x22\x27]',
}
findings=[]; scanned=0
for file in ROOT.rglob('*'):
 if not file.is_file() or any(p in ('.venv','node_modules','.git','__pycache__','audit') for p in file.relative_to(ROOT).parts): continue
 if file.stat().st_size>20_000_000: continue
 data=file.read_bytes(); scanned+=1
 for name,pattern in patterns.items():
  if re.search(pattern,data): findings.append({'path':str(file.relative_to(ROOT)),'category':name,'action':'review locally; no value is included in this report'})
out={'files_scanned':scanned,'git_history':'not available: no Git repository','findings':findings,'limits':'Pattern scan cannot prove absence of secrets; binary session stores and external originals need separate review.'}
(ROOT/'audit').mkdir(exist_ok=True)
(ROOT/'audit/secret-scan.json').write_text(json.dumps(out,indent=2))
print(json.dumps({'files_scanned':scanned,'potential_findings':len(findings)}))
