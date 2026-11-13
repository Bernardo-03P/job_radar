"""Worker de PDF: stdin/stdout em RAM, CPU/memória limitadas, sem arquivo temporário."""
import json
import os
import sys

_job_handle = None


def limit_resources():
    memory = 512 * 1024 * 1024
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                        ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IO), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                        ("peak_job", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        limits = ExtendedLimits()
        limits.basic.flags = 0x100 | 0x2  # limite de memória por processo e CPU
        limits.basic.process_time = 10 * 10000000
        limits.process_memory = memory
        global _job_handle
        _job_handle = kernel.CreateJobObjectW(None, None)
        if (not _job_handle or not kernel.SetInformationJobObject(
                _job_handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                or not kernel.AssignProcessToJobObject(_job_handle, kernel.GetCurrentProcess())):
            raise OSError("Limites do worker indisponíveis")
    else:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))


def main():
    try:
        limit_resources()
        from fastapi import HTTPException

        from app.services.pdf_parser import MAX_SIZE, PDFParserService
        payload = sys.stdin.buffer.read(MAX_SIZE + 1)
        if len(payload) > MAX_SIZE:
            result = {"status": 400, "detail": "Arquivo excede o limite de 5MB."}
        else:
            try:
                result = {"status": 200, "text": PDFParserService._extract(payload)}
            except HTTPException as error:
                result = {"status": error.status_code, "detail": error.detail}
    except MemoryError:
        result = {"status": 400, "detail": "O PDF excede o limite seguro de processamento."}
    except Exception:
        result = {"status": 400, "detail": "Não foi possível processar o PDF com segurança."}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
