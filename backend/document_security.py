"""Fail-closed upload validation; PDF parsing runs in a bounded child process."""
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILE=10_000_000
MAX_TEXT=200_000

def validate_document(data, filename, kind, content_type=None):
    name=Path(filename or '').name.lower()
    if kind not in ('pdf','xlsx','csv') or not name.endswith('.'+kind):
        raise ValueError('Supported imports: text PDF CV, XLSX tracker, UTF-8 CSV tracker')
    if any('.'+ext+'.' in name for ext in ('exe','com','bat','cmd','ps1','js','vbs','scr','dll')):
        raise ValueError('Executable or double-extension upload rejected')
    if not data or len(data)>MAX_FILE: raise ValueError('File must be non-empty and no larger than 10 MB')
    allowed={'pdf':{'application/pdf'},'xlsx':{'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},'csv':{'text/csv','application/csv','text/plain','application/vnd.ms-excel'}}
    if content_type and content_type.split(';')[0].lower() not in allowed[kind]|{'application/octet-stream'}:
        raise ValueError('The declared file type does not match this import')
    if data.startswith((b'MZ',b'\x7fELF')): raise ValueError('Executable content rejected')
    if kind=='pdf':
        if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-2048:]: raise ValueError('Malformed PDF')
        if any(token in data for token in (b'/JavaScript',b'/JS ',b'/Launch',b'/EmbeddedFile',b'/OpenAction')):
            raise ValueError('Active or embedded PDF content is not supported')
    elif kind=='xlsx':
        if not data.startswith(b'PK\x03\x04'): raise ValueError('Not an XLSX archive')
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos=archive.infolist(); names={i.filename for i in infos}
                if len(infos)>1000 or sum(i.file_size for i in infos)>30_000_000: raise ValueError('Archive decompression limit exceeded')
                if not {'[Content_Types].xml','xl/workbook.xml'}<=names: raise ValueError('Not an XLSX workbook; DOCX and macro files are unsupported')
                for item in infos:
                    p=PurePosixPath(item.filename)
                    if p.is_absolute() or '..' in p.parts or '\\' in item.filename or item.flag_bits&1:
                        raise ValueError('Unsafe archive entry')
                    if item.file_size>10_000_000 or item.file_size>max(item.compress_size,1)*200:
                        raise ValueError('Archive compression ratio or entry limit exceeded')
                    if 'vbaproject' in item.filename.lower() or 'externallinks/' in item.filename.lower():
                        raise ValueError('Macros and external workbook links are unsupported')
                    if item.filename.endswith(('.xml','.rels')):
                        xml=archive.read(item)
                        if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper(): raise ValueError('XML entities are unsupported')
        except (zipfile.BadZipFile,RuntimeError,EOFError) as exc:
            raise ValueError('Malformed XLSX archive') from None
    else:
        try: text=data.decode('utf-8-sig')
        except UnicodeDecodeError: raise ValueError('CSV must be UTF-8 text') from None
        if '\x00' in text or '<html' in text.lower() or '<script' in text.lower(): raise ValueError('CSV contains unsupported binary or HTML content')
    return data

def extract_pdf(path):
    path=Path(path).resolve()
    validate_document(path.read_bytes(),path.name,'pdf')
    try:
        result=subprocess.run([sys.executable,'-m','backend.pdf_worker',str(path)],
                              cwd=Path(__file__).resolve().parents[1],capture_output=True,timeout=20)
        if result.returncode!=0: raise ValueError('PDF could not be safely parsed. Your existing profile has not been replaced.')
        if len(result.stdout)>MAX_TEXT*6+100: raise ValueError('Extracted CV is too long')
        return json.loads(result.stdout)['text']
    except subprocess.TimeoutExpired:
        raise ValueError('PDF parsing exceeded 20 seconds. Use a smaller text-based PDF.') from None

