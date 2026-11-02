"""Observe Windows writes even when coarse timestamps and bytes are restored."""
import os
from pathlib import Path
import struct

_windows = None


def api():
    global _windows
    if _windows is None:
        import ctypes as c
        from ctypes import wintypes as w
        from types import SimpleNamespace
        class Overlapped(c.Structure):
            _fields_ = [('Internal', c.c_size_t), ('InternalHigh', c.c_size_t),
                        ('Offset', w.DWORD), ('OffsetHigh', w.DWORD), ('hEvent', w.HANDLE)]
        k = c.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateFileW': ([w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
            'CreateEventW': ([c.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR], w.HANDLE),
            'ReadDirectoryChangesW': ([w.HANDLE, c.c_void_p, w.DWORD, w.BOOL, w.DWORD,
                                      c.POINTER(w.DWORD), c.POINTER(Overlapped), c.c_void_p], w.BOOL),
            'GetOverlappedResult': ([w.HANDLE, c.POINTER(Overlapped), c.POINTER(w.DWORD), w.BOOL], w.BOOL),
            'CancelIoEx': ([w.HANDLE, c.POINTER(Overlapped)], w.BOOL),
            'ResetEvent': ([w.HANDLE], w.BOOL), 'CloseHandle': ([w.HANDLE], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(k, name)
            function.argtypes, function.restype = args, result
        _windows = SimpleNamespace(c=c, w=w, k=k, Overlapped=Overlapped)
    return _windows


def native_path(path):
    value = str(path)
    if value.startswith('\\\\?\\'):
        return value
    return '\\\\?\\UNC\\'+value[2:] if value.startswith('\\\\') else '\\\\?\\'+value


class DirectoryWatch:
    def __init__(self, directory, recursive):
        self.directory, self.recursive = directory, recursive
        a = api()
        self.handle = a.k.CreateFileW(native_path(directory), 1, 7, None, 3, 0x42000000, None)
        if self.handle == a.c.c_void_p(-1).value:
            raise a.c.WinError(a.c.get_last_error())
        self.event = a.k.CreateEventW(None, True, False, None)
        if not self.event:
            a.k.CloseHandle(self.handle)
            raise a.c.WinError(a.c.get_last_error())
        self.overlapped = a.Overlapped()
        self.overlapped.hEvent = self.event
        self.buffer = a.c.create_string_buffer(65536)
        try:
            self.arm()
        except BaseException:
            self.close()
            raise

    def arm(self):
        a = api()
        a.k.ResetEvent(self.event)
        # Names, directories, attributes, size and writes; reads do not matter.
        if not a.k.ReadDirectoryChangesW(self.handle, self.buffer, len(self.buffer),
                self.recursive, 0x1F, None, a.c.byref(self.overlapped), None):
            raise a.c.WinError(a.c.get_last_error())

    def poll(self):
        a, changed = api(), set()
        for _ in range(64):
            size = a.w.DWORD()
            if not a.k.GetOverlappedResult(self.handle, a.c.byref(self.overlapped), a.c.byref(size), False):
                error = a.c.get_last_error()
                if error == 996:  # ERROR_IO_INCOMPLETE: subscription is still pending.
                    return changed
                raise a.c.WinError(error)
            if not size.value:
                raise OSError('Input change notification buffer overflow; reload validation inputs')
            raw, offset = bytes(self.buffer)[:size.value], 0
            while True:
                step, action, length = struct.unpack_from('<III', raw, offset)
                name = raw[offset+12:offset+12+length].decode('utf-16-le')
                changed.add((self.directory/name, action))
                if not step:
                    break
                offset += step
            self.arm()
        raise OSError('Input change notifications are continuously busy; retry a fresh stage')

    def close(self):
        if self.handle is not None:
            a = api()
            a.k.CancelIoEx(self.handle, a.c.byref(self.overlapped))
            size = a.w.DWORD()
            a.k.GetOverlappedResult(self.handle, a.c.byref(self.overlapped), a.c.byref(size), True)
            a.k.CloseHandle(self.handle)
            a.k.CloseHandle(self.event)
            self.handle = None


class Changes:
    def __init__(self):
        self.watches, self.baselines = {}, {}
        self.modified, self.names = {}, {}
        self.sequence = 0

    def watch(self, path):
        if os.name != 'nt':
            return
        parent = path.parent
        while not parent.is_dir():
            parent = parent.parent
        key = parent, parent != path.parent
        if key not in self.watches:
            self.watches[key] = DirectoryWatch(*key)
        # A newly produced CLI receipt becomes an input only when first read.
        # Earlier notifications from an existing ancestor subscription must not
        # invalidate that initial snapshot or erase another input's history.
        self.poll()
        self.baselines[path] = self.sequence

    def poll(self):
        for watcher in self.watches.values():
            for name, action in watcher.poll():
                self.sequence += 1
                self.modified[name] = self.sequence
                if action != 3:
                    self.names[name] = self.sequence

    def touched(self, path):
        # A sibling output updates its directory's write time. Only a name
        # change of an ancestor, rather than that metadata update, affects us.
        baseline = self.baselines.get(path, 0)
        return (self.modified.get(path, 0) > baseline
                or any(self.names.get(parent, 0) > baseline for parent in path.parents))

    def acknowledge(self, path):
        self.poll()
        path = Path(path)
        self.baselines[path] = self.sequence

    def close(self):
        for watcher in self.watches.values():
            watcher.close()


# Module import is serialized; initialise immutable API signatures once before
# independent validation threads can create directory subscriptions.
if os.name == 'nt':
    api()
