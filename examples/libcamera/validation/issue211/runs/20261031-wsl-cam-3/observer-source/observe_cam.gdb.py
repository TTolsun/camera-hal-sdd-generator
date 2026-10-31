"""GDB observation only: no inferior calls, memory writes, or code patches.

Run with --nx --nh and auto-load disabled. Breakpoints affect timing; neither
callback return nor capture performance is measured by these observations.
"""
import hashlib
import json
import os
from pathlib import Path

import gdb

out = Path(os.environ['ISSUE211_OUT'])
source = Path(os.environ['ISSUE211_SOURCE'])
events = (out / 'events.jsonl').open('x')
allocations = (out / 'allocations.jsonl').open('x')
buffers = (out / 'buffers.jsonl').open('x')
failures = []
loaded = False


def emit(stream, value):
    stream.write(json.dumps(value, sort_keys=True) + '\n')
    stream.flush()
    gdb.write('OBSERVATION ' + json.dumps(value, sort_keys=True) + '\n')


def archive_loaded():
    global loaded
    if loaded:
        return
    pid = gdb.selected_inferior().pid
    maps = Path(f'/proc/{pid}/maps').read_text()
    (out / 'loaded.maps').write_text(maps)
    paths = {line.split(maxsplit=5)[5] for line in maps.splitlines()
             if len(line.split(maxsplit=5)) == 6 and line.split(maxsplit=5)[5].startswith('/')}
    hashes = {}
    for name in paths:
        path = Path(name)
        if path.is_file():
            with path.open('rb') as stream:
                hashes[str(path.resolve())] = hashlib.file_digest(stream, 'sha256').hexdigest()
    executable = Path(f'/proc/{pid}/exe').resolve()
    (out / 'loaded.json').write_text(json.dumps(dict(pid=pid, executable=str(executable), files=hashes), indent=2) + '\n')
    loaded = True


def private_pointer(value):
    """Read libstdc++ unique_ptr base fields using DWARF, without calling get()."""
    candidates = []

    def visit(item, depth=0):
        if depth > 8:
            return
        for field in item.type.strip_typedefs().fields():
            if field.is_base_class:
                visit(item.cast(field.type), depth + 1)
            elif field.name:
                child = item[field.name]
                if field.name == '_M_head_impl' and child.type.code == gdb.TYPE_CODE_PTR:
                    candidates.append(child)
                elif child.type.strip_typedefs().code == gdb.TYPE_CODE_STRUCT:
                    visit(child, depth + 1)
    visit(value)
    if len(candidates) != 1:
        raise RuntimeError('Ambiguous unique_ptr DWARF storage')
    return candidates[0]


class Observation(gdb.Breakpoint):
    def __init__(self, location, point):
        super().__init__(location, internal=False)
        self.point = point

    def stop(self):
        try:
            archive_loaded()
            thread = gdb.selected_thread()
            frame = gdb.newest_frame()
            value = dict(point=self.point, pid=thread.ptid[0], tid=thread.ptid[1],
                         location=self.location)
            if self.point == 'allocator-return':
                dma = int(frame.read_var('ret'))
                create = frame.read_var('create')
                pid = gdb.selected_inferior().pid
                fdroot = Path(f'/proc/{pid}/fd')
                providers = {p.name: os.readlink(p) for p in fdroot.iterdir()
                             if p.is_symlink() and os.readlink(p) == '/dev/udmabuf'}
                value.update(result=dma, backing_fd=int(create['memfd']), size=int(create['size']),
                             providers=providers,
                             dmabuf_link=os.readlink(fdroot / str(dma)) if dma >= 0 else None,
                             fdinfo=Path(f'/proc/{pid}/fdinfo/{dma}').read_text() if dma >= 0 else None)
                emit(allocations, value)
            else:
                request = frame.read_var('request')
                obj = request.dereference()
                private = private_pointer(obj['d_']).cast(gdb.lookup_type('libcamera::Request::Private').pointer())
                value.update(request=str(request), sequence=int(private.dereference()['sequence_']),
                             status=int(obj['status_']), cookie=int(obj['cookie_']))
                if self.point == 'buffer-metadata':
                    metadata = frame.read_var('metadata')
                    value.update(buffer_status=int(metadata['status']), buffer_sequence=int(metadata['sequence']))
                    emit(buffers, value)
                else:
                    emit(events, value)
            gdb.execute('info threads')
            gdb.execute('bt 8')
        except Exception as exc:
            failures.append(str(exc))
            gdb.write('OBSERVATION_FAILED ' + repr(exc) + '\n')
        return False


session = source / 'src/apps/cam/camera_session.cpp'
allocator = source / 'src/libcamera/dma_buf_allocator.cpp'
processing = [i for i, line in enumerate(session.read_text().splitlines(), 1) if line.strip() == 'captureCount_++;']
buffer_lines = [i for i, line in enumerate(session.read_text().splitlines(), 1) if 'info << " " << streamNames_[stream]' in line]
allocate_lines = allocator.read_text().splitlines()
allocate = [i + 2 for i, line in enumerate(allocate_lines)
            if 'int ret = ::ioctl(providerHandle_.get(), UDMABUF_CREATE, &create);' in line]
if len(processing) != 1 or len(allocate) != 1 or len(buffer_lines) != 1:
    raise RuntimeError('Source observation window changed')
Observation('CameraSession::requestComplete', 'callback-entry')
Observation(f'{session}:{processing[0]}', 'frame-processed')
Observation(f'{session}:{buffer_lines[0]}', 'buffer-metadata')
Observation(f'{allocator}:{allocate[0]}', 'allocator-return')


def exited(event):
    (out / 'inferior-exit.json').write_text(json.dumps(dict(exit_code=getattr(event, 'exit_code', None),
                                                         observation_failures=failures)) + '\n')


gdb.events.exited.connect(exited)
gdb.execute('run')
if failures:
    gdb.execute('quit 1')
