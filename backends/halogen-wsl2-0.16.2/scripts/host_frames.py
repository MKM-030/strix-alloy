"""Direct Windows physical/commit telemetry; no subprocess or GPU initialization."""
import ctypes

class Memory(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
        (key, ctypes.c_uint64) for key in ('total', 'available', 'total_page', 'available_page',
                                          'total_virtual', 'available_virtual', 'extended')]


class Performance(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint32)] + [
        (key, ctypes.c_size_t) for key in ('commit_total', 'commit_limit', 'commit_peak',
                                          'physical_total', 'physical_available', 'system_cache',
                                          'kernel_total', 'kernel_paged', 'kernel_nonpaged', 'page_size')] + [
        (key, ctypes.c_uint32) for key in ('handle_count', 'process_count', 'thread_count')]


def frame():
    m, p = Memory(), Performance()
    m.length, p.length = ctypes.sizeof(m), ctypes.sizeof(p)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise OSError('GlobalMemoryStatusEx_failed')
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p), p.length):
        raise OSError('GetPerformanceInfo_failed')
    return dict(available_bytes=m.available, committed_bytes=p.commit_total*p.page_size,
                commit_limit_bytes=p.commit_limit*p.page_size,
                commit_headroom_bytes=(p.commit_limit-p.commit_total)*p.page_size)

