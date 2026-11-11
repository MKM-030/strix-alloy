"""Bounded static AMD64 PE closure. Reads bytes only; never loads or invokes code."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

DEFAULT_LIMITS = dict(max_modules=128, max_file_bytes=64 * 1024 * 1024,
    max_total_bytes=512 * 1024 * 1024, max_sections=96,
    max_descriptors=256, max_thunks=65536, max_exports=65536,
    max_total_imports=262144, max_string=4096, max_forward_depth=16,
    max_directory_entries=65536)
DEFAULT_PINS = {
    'qwen3_5vl_npu.dll': 'd77388dcd21fcd7422005d0f780a044142d525e3afaafef3bcb9e980b8c18501',
    'xrt_coreutil.dll': 'd0dce13280a0d668b497d4fcabdcb43f1a7353e466af3acabd98c6df7607ed8e'}


class PEError(ValueError):
    pass


def require(value, message):
    if not value:
        raise PEError(message)


def unlinked(path):
    return not any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
                   for p in (path, *path.parents))


class PEImage:
    def __init__(self, path, *, limits=None):
        self.path = Path(path).absolute()
        self.limits = dict(DEFAULT_LIMITS, **(limits or {}))
        require(unlinked(self.path) and self.path.is_file(), 'Missing or linked PE file')
        require(self.path.stat().st_size <= self.limits['max_file_bytes'], 'PE file byte limit exceeded')
        self.data = self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        require(self.data[:2] == b'MZ', 'Missing DOS signature')
        pe = self.u32(0x3c)
        require(self.take(pe, 4) == b'PE\0\0', 'Missing PE signature')
        require(self.u16(pe + 4) == 0x8664, 'Requires AMD64 PE')
        count = self.u16(pe + 6)
        require(0 < count <= self.limits['max_sections'], 'PE section count outside bound')
        optional_size = self.u16(pe + 20)
        optional = pe + 24
        self.take(optional, optional_size)
        require(optional_size >= 112 and self.u16(optional) == 0x20b, 'Requires bounded PE32+ optional header')
        self.image_base = self.u64(optional + 24)
        self.header_size = self.u32(optional + 60)
        directories = self.u32(optional + 108)
        require(directories <= 16 and 112 + directories * 8 <= optional_size,
                'PE directory count exceeds optional header')
        self.directories = [struct.unpack('<II', self.take(optional + 112 + i * 8, 8))
                            for i in range(directories)]
        self.sections = []
        table = optional + optional_size
        for i in range(count):
            row = self.take(table + i * 40, 40)
            virtual_size, rva, raw_size, raw = struct.unpack_from('<IIII', row, 8)
            self.take(raw, raw_size)
            self.sections.append((rva, max(virtual_size, raw_size), raw, raw_size))
        self.exports, self.ordinals = self.read_exports()
        self.import_count = 0
        self.imports = self.read_imports(False) + self.read_imports(True)

    def take(self, offset, size):
        require(type(offset) is int and type(size) is int and offset >= 0 and size >= 0
                and offset + size <= len(self.data), 'PE file range outside bytes')
        return self.data[offset:offset + size]

    def u16(self, offset):
        return struct.unpack('<H', self.take(offset, 2))[0]

    def u32(self, offset):
        return struct.unpack('<I', self.take(offset, 4))[0]

    def u64(self, offset):
        return struct.unpack('<Q', self.take(offset, 8))[0]

    def offset(self, rva, size=1):
        require(0 <= rva <= 0xffffffff and size >= 0, 'Invalid PE RVA')
        if rva < self.header_size and rva + size <= min(self.header_size, len(self.data)):
            return rva
        matches = [(raw + rva - start) for start, length, raw, raw_size in self.sections
                   if start <= rva and rva + size <= start + length
                   and rva - start + size <= raw_size]
        require(len(matches) == 1, 'PE RVA is unmapped, virtual-only or ambiguous')
        return matches[0]

    def string(self, rva):
        chars = bytearray()
        for i in range(self.limits['max_string']):
            byte = self.data[self.offset(rva + i)]
            if byte == 0:
                try:
                    return chars.decode('ascii')
                except UnicodeDecodeError as error:
                    raise PEError('Non-ASCII PE symbol/module') from error
            chars.append(byte)
        raise PEError('PE string length bound exceeded')

    def directory(self, index):
        return self.directories[index] if index < len(self.directories) else (0, 0)

    def read_exports(self):
        rva, size = self.directory(0)
        if rva == size == 0:
            return {}, {}
        require(rva and size >= 40, 'Invalid PE export directory')
        base = self.offset(rva, 40)
        ordinal_base, functions, names, function_rva, names_rva, ordinal_rva = struct.unpack('<IIIIII', self.take(base + 16, 24))
        require(functions <= self.limits['max_exports'] and names <= functions,
                'PE export count outside bound')
        self.offset(function_rva, functions * 4)
        self.offset(names_rva, names * 4)
        self.offset(ordinal_rva, names * 2)
        by_ordinal = {}
        for i in range(functions):
            value = self.u32(self.offset(function_rva + i * 4, 4))
            if not value:
                continue
            if rva <= value < rva + size:
                target = dict(forwarder=self.string(value))
            else:
                # Data exports can name loader-zeroed .bss rather than file bytes.
                require(any(start <= value < start + length
                            for start, length, raw, raw_size in self.sections),
                        'Export target RVA outside virtual image sections')
                target = dict(rva=value)
            by_ordinal[ordinal_base + i] = target
        named = {}
        for i in range(names):
            name = self.string(self.u32(self.offset(names_rva + i * 4, 4)))
            ordinal = ordinal_base + self.u16(self.offset(ordinal_rva + i * 2, 2))
            require(name and name not in named and ordinal in by_ordinal, 'Invalid or duplicate named export')
            named[name] = by_ordinal[ordinal]
        return named, by_ordinal

    def read_imports(self, delayed):
        rva, size = self.directory(13 if delayed else 1)
        if rva == size == 0:
            return []
        width = 32 if delayed else 20
        require(rva and size >= width, 'Invalid PE import directory')
        result = []
        for index in range(self.limits['max_descriptors']):
            require((index + 1) * width <= size, 'Import descriptor terminator outside directory')
            raw = self.take(self.offset(rva + index * width, width), width)
            if not any(raw):
                return result
            fields = struct.unpack('<' + 'I' * (width // 4), raw)
            if delayed:
                require(fields[0] == 1, 'Unsupported VA-based or reserved delay-import attributes')
                name_rva, thunk_rva = fields[1], fields[4]
            else:
                name_rva, thunk_rva = fields[3], fields[0] or fields[4]
            require(name_rva and thunk_rva, 'Missing import module or thunk table')
            symbols = []
            for item in range(self.limits['max_thunks']):
                thunk = self.u64(self.offset(thunk_rva + item * 8, 8))
                if not thunk:
                    break
                self.import_count += 1
                require(self.import_count <= self.limits['max_total_imports'],
                        'PE import-symbol storage bound exceeded')
                if thunk & (1 << 63):
                    require(thunk & ~((1 << 63) | 0xffff) == 0, 'Reserved ordinal thunk bits')
                    symbols.append(thunk & 0xffff)
                else:
                    self.offset(thunk, 2)
                    symbols.append(self.string(thunk + 2))
            else:
                raise PEError('Import thunk terminator bound exceeded')
            result.append(dict(module=self.string(name_rva), symbols=symbols, delayed=delayed))
        raise PEError('Import descriptor count bound exceeded')


def module_name(name):
    require(type(name) is str and name and len(name) <= 260
            and not any(c in name for c in '/\\:') and '..' not in name,
            'Invalid import module basename')
    value = name.lower()
    return value if '.' in value else value + '.dll'


def inspect_closure(exe, portable, system32=Path('C:/Windows/System32'), expected_pins=None, limits=None):
    limits = dict(DEFAULT_LIMITS, **(limits or {}))
    require(all(type(v) is int and v > 0 for v in limits.values()), 'Limits must be positive integers')
    exe, portable, system32 = (Path(p).absolute() for p in (exe, portable, system32))
    pins = dict(DEFAULT_PINS if expected_pins is None else expected_pins)
    errors, contracts, resolved, edges, images, queue = [], set(), [], [], {}, []
    OS_internal_imports_not_expanded = set()
    failed_images = {}
    total_bytes = total_imports = 0
    directory_cache = {}

    def directory_files(root):
        if root not in directory_cache:
            require(root.is_dir() and unlinked(root), 'Missing or linked dependency directory')
            values = {}
            for i, path in enumerate(root.iterdir()):
                require(i < limits['max_directory_entries'], 'Directory entry count bound exceeded')
                if path.is_file():
                    key = path.name.lower()
                    require(key not in values, 'Case-ambiguous dependency filename')
                    values[key] = path
            directory_cache[root] = values
        return directory_cache[root]

    def load(path, name, role):
        nonlocal total_bytes
        key = str(path.resolve()).lower()
        if key in images:
            return images[key]
        if key in failed_images:
            raise PEError(failed_images[key])
        require(len(images) + len(failed_images) < limits['max_modules'], 'Module count bound exceeded')
        size = path.stat().st_size
        require(size + total_bytes <= limits['max_total_bytes'], 'Total PE bytes bound exceeded')
        total_bytes += size
        try:
            image = PEImage(path, limits=limits)
            if name in pins:
                require(image.sha256 == pins[name], 'Pinned dependency hash differs: ' + name)
        except (PEError, OSError) as error:
            failed_images[key] = str(error)
            raise
        images[key] = image
        image.audit_imports = role in ('entry', 'portable') or name == 'xrt_coreutil.dll'
        queue.append(image)
        resolved.append(dict(name=name, role=role, path=str(path), bytes=len(image.data),
            sha256=image.sha256, named_exports=len(image.exports), ordinal_exports=len(image.ordinals)))
        return image

    def dependency(name):
        name = module_name(name)
        if name.startswith(('api-ms-', 'ext-ms-')):
            contracts.add(name)
            return None
        # Model the EXE-directory precedence, but refuse unapproved shadow DLLs.
        roots = list(dict.fromkeys((exe.parent, portable, system32)))
        for root in roots:
            match = directory_files(root).get(name)
            if match is not None:
                require(root in (portable, system32), 'Unapproved EXE-directory dependency shadow: ' + str(match))
                return load(match, name, 'portable' if root == portable else 'system32')
        raise PEError('Unresolved module: ' + name)

    def symbol(image, wanted, chain=()):
        require(len(chain) < limits['max_forward_depth'], 'Forwarder depth bound exceeded')
        key = (str(image.path).lower(), wanted)
        require(key not in chain, 'Export forwarder cycle')
        target = (image.ordinals if type(wanted) is int else image.exports).get(wanted)
        require(target is not None, 'Missing export ' + str(wanted) + ' in ' + image.path.name)
        if 'forwarder' in target:
            forward = target['forwarder']
            require('.' in forward, 'Malformed export forwarder')
            owner, entry = forward.rsplit('.', 1)
            if entry.startswith('#'):
                require(entry[1:].isdigit() and 0 <= int(entry[1:]) <= 65535, 'Invalid forwarder ordinal')
                entry = int(entry[1:])
            require(entry != '', 'Empty forwarded symbol')
            other = dependency(owner)
            edges.append(dict(source=str(image.path), symbol=wanted, forwarder=forward,
                              unresolved_API_set=other is None))
            if other is not None:
                symbol(other, entry, (*chain, key))

    try:
        load(exe, exe.name.lower(), 'entry')
        index = 0
        while index < len(queue):
            image = queue[index]
            index += 1
            if not image.audit_imports:
                if image.imports:
                    OS_internal_imports_not_expanded.add(str(image.path))
                continue
            for imported in image.imports:
                try:
                    other = dependency(imported['module'])
                    for wanted in imported['symbols']:
                        total_imports += 1
                        require(total_imports <= limits['max_total_imports'], 'Total import-symbol bound exceeded')
                        if other is not None:
                            symbol(other, wanted)
                    edges.append(dict(source=str(image.path), module=imported['module'],
                        symbols=imported['symbols'], delayed=imported['delayed'], unresolved_API_set=other is None))
                except (PEError, OSError) as error:
                    errors.append(dict(source=str(image.path), module=imported['module'], message=str(error)))
    except (PEError, OSError) as error:
        errors.append(dict(source=str(exe), message=str(error)))
    complete = not errors and not contracts and not OS_internal_imports_not_expanded
    return dict(schema='halogen.growing-native-static-PE-preflight.v1',
        passed=not errors, full_static_closure_complete=complete,
        pass_scope='Static payload/module symbol checks; Windows API-set mapping is left to the normal OS loader.',
        payload_closure_passed=not errors, unresolved_API_set_contracts=sorted(contracts),
        API_set_namespace_resolved=False,
        OS_internal_import_modules_not_expanded=sorted(OS_internal_imports_not_expanded),
        OS_internal_import_policy='Inspect required OS exports/forwarders; leave OS-internal dependency trees to normal Windows loader resolution.',
        API_set_policy='Contracts are reported unresolved; no guessed host-DLL mapping or full-pass claim.',
        modules=resolved, edges=edges, errors=errors, limits=limits,
        total_PE_bytes=total_bytes, total_import_symbols=total_imports,
        expected_pins=pins, DLL_loaded=False, subprocesses_started=0, hardware_accessed=False,
        dynamic_LoadLibrary_or_plugin_dependencies_qualified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--portable', type=Path, required=True)
    parser.add_argument('--system32', type=Path, default=Path('C:/Windows/System32'))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = inspect_closure(args.exe, args.portable, args.system32)
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps(dict(passed=report['passed'], payload_closure_passed=report['payload_closure_passed'],
        unresolved_API_sets=len(report['unresolved_API_set_contracts']), errors=report['errors'])))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
