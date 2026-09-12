"""No network or shell operations. Isolated PDF parser with OS memory limits."""
import json
import os
import sys

def limit_memory():
    limit=512*1024*1024
    if os.name!='nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(limit,limit))
        return None
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_=[('process_time',c.c_int64),('job_time',c.c_int64),('flags',w.DWORD),('min_ws',c.c_size_t),('max_ws',c.c_size_t),('active',w.DWORD),('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(c.Structure):
        _fields_=[(name,c.c_uint64) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    class Extended(c.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',c.c_size_t),('job_memory',c.c_size_t),('peak_process',c.c_size_t),('peak_job',c.c_size_t)]
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.restype=w.HANDLE
    kernel.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR]
    kernel.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
    kernel.GetCurrentProcess.restype=w.HANDLE
    handle=kernel.CreateJobObjectW(None,None)
    info=Extended(); info.basic.flags=0x100; info.process_memory=limit
    if not handle or not kernel.SetInformationJobObject(handle,9,c.byref(info),c.sizeof(info)) or not kernel.AssignProcessToJobObject(handle,kernel.GetCurrentProcess()):
        raise RuntimeError('Could not establish parser memory limit')
    return handle

def main():
    handle=limit_memory()  # Keep the Windows job handle alive until this process exits.
    from pypdf import PdfReader
    reader=PdfReader(sys.argv[1],strict=True)
    if reader.is_encrypted or len(reader.pages)>100: raise ValueError('Unsupported document')
    sections=[]; size=0
    for page in reader.pages:
        value=page.extract_text() or ''; size+=len(value)
        if size>200_000: raise ValueError('Text limit exceeded')
        sections.append(value)
    sys.stdout.buffer.write(json.dumps({'text':'\n'.join(sections)},ensure_ascii=True).encode('utf-8'))

if __name__=='__main__':
    try: main()
    except Exception: sys.exit(2)  # Never emit document contents into error logs.
