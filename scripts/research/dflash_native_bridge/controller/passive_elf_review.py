import hashlib
import re
import struct


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Elf:
    def __init__(self, data):
        self.data = data
        if data[:7] != b'\x7fELF\x02\x01\x01' or struct.unpack_from('<HH', data, 16) != (3, 62):
            raise ValueError('Expected Linux x86-64 little-endian ET_DYN')
        phoff, shoff = struct.unpack_from('<QQ', data, 32)
        phsize, phnum, shsize, shnum, shstrndx = struct.unpack_from('<HHHHH', data, 54)
        if phsize != 56 or shsize != 64 or phnum > 64 or shnum > 256:
            raise ValueError('ELF table geometry outside narrow bounds')
        if phoff + phsize * phnum > len(data) or shoff + shsize * shnum > len(data):
            raise ValueError('ELF header tables outside file')
        self.segments = []
        for i in range(phnum):
            kind, flags, off, va, _, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, phoff + i * phsize)
            if off + filesz > len(data):
                raise ValueError('ELF segment outside file')
            self.segments.append({'index': i, 'type': kind, 'flags': flags, 'file_offset': off,
                'rva': va, 'file_bytes': filesz, 'memory_bytes': memsz, 'alignment': align})
        raw = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * shsize) for i in range(shnum)]
        names = raw[shstrndx]
        if names[5] > 65536:
            raise ValueError('Section string table bound exceeded')
        self.sections = {}
        for value in raw:
            start = names[4] + value[0]
            end = data.find(b'\0', start, names[4] + names[5])
            name = data[start:end].decode('ascii')
            self.sections[name] = {'type': value[1], 'flags': value[2], 'rva': value[3],
                'file_offset': value[4], 'bytes': value[5], 'alignment': value[8]}
        self.phnum = phnum

    def mapped(self, offset, size, executable=False):
        spans = [x for x in self.segments if x['type'] == 1 and
            (not executable or x['flags'] == 5) and x['file_offset'] <= offset and
            offset + size <= x['file_offset'] + x['file_bytes']]
        if len(spans) != 1:
            raise ValueError('File span must map to one relevant PT_LOAD')
        value = dict(spans[0])
        value['span_file_offset'] = offset
        value['span_rva'] = value['rva'] + offset - value['file_offset']
        return value

    def offset(self, rva, size=1):
        spans = [x for x in self.segments if x['type'] == 1 and x['rva'] <= rva and
            rva + size <= x['rva'] + x['file_bytes']]
        if len(spans) != 1:
            raise ValueError('RVA is not a unique file-backed PT_LOAD span')
        return spans[0]['file_offset'] + rva - spans[0]['rva']

    def section(self, rva):
        spans = [(name, value) for name, value in self.sections.items() if value['flags'] & 2 and
            value['rva'] <= rva < value['rva'] + value['bytes']]
        if len(spans) != 1:
            raise ValueError('Target must map to one allocated ELF section')
        return spans[0]

    def relocation_names(self):
        symbols, strings = self.sections['.dynsym'], self.sections['.dynstr']
        result = {}
        for name in ('.rela.dyn', '.rela.plt'):
            section = self.sections.get(name)
            if section is None:
                continue
            if section['bytes'] > 1024 * 1024 or section['bytes'] % 24:
                raise ValueError('Relocation table bound exceeded')
            for at in range(section['file_offset'], section['file_offset'] + section['bytes'], 24):
                rva, info, addend = struct.unpack_from('<QQq', self.data, at)
                symbol_index = info >> 32
                symbol_at = symbols['file_offset'] + symbol_index * 24
                if symbol_at + 24 > symbols['file_offset'] + symbols['bytes']:
                    raise ValueError('Dynamic symbol index outside table')
                name_at = strings['file_offset'] + struct.unpack_from('<I', self.data, symbol_at)[0]
                end = self.data.find(b'\0', name_at, strings['file_offset'] + strings['bytes'])
                symbol = self.data[name_at:end].decode('ascii')
                result[rva] = {'symbol': symbol, 'relocation_type': info & 0xffffffff, 'addend': addend}
        return result

    def unwind_range(self, site_rva):
        section = self.sections['.eh_frame_hdr']
        off, base = section['file_offset'], section['rva']
        if self.data[off:off + 4] != b'\x01\x1b\x03\x3b':
            raise ValueError('Existing ELF unwind encoding unsupported; do not invent decoder')
        count = struct.unpack_from('<I', self.data, off + 8)[0]
        if count > 200000 or 12 + count * 8 > section['bytes']:
            raise ValueError('Unwind header table bound exceeded')
        entry = None
        for i in range(count):
            address, fde = struct.unpack_from('<ii', self.data, off + 12 + i * 8)
            address, fde = base + address, base + fde
            if address > site_rva:
                break
            entry = (address, fde)
        if entry is None:
            raise ValueError('No containing preflight unwind candidate')
        initial, fde_rva = entry
        fde_off = self.offset(fde_rva, 16)
        length, cie_relative = struct.unpack_from('<II', self.data, fde_off)
        if length < 12 or length > 65536:
            raise ValueError('FDE record bound exceeded')
        cie_off = fde_off + 4 - cie_relative
        cie_length, cie_id = struct.unpack_from('<II', self.data, cie_off)
        if cie_id != 0 or cie_length > 4096:
            raise ValueError('CIE record unsupported')
        at = cie_off + 8
        version = self.data[at]
        at += 1
        end = self.data.find(b'\0', at, cie_off + 4 + cie_length)
        augmentation = self.data[at:end].decode('ascii')
        at = end + 1

        def leb(signed=False):
            nonlocal at
            result, shift = 0, 0
            for _ in range(10):
                part = self.data[at]
                at += 1
                result |= (part & 127) << shift
                shift += 7
                if not part & 128:
                    if signed and part & 64:
                        result -= 1 << shift
                    return result
            raise ValueError('CIE LEB bound exceeded')

        code_align, data_align = leb(), leb(True)
        if version == 1:
            return_register = self.data[at]
            at += 1
        else:
            return_register = leb()
        if augmentation not in ('zR', 'zPLR'):
            raise ValueError('CIE augmentation unsupported for narrow range check')
        augmentation_length = leb()
        augmentation_end = at + augmentation_length
        encoding = None
        for marker in augmentation[1:]:
            if marker == 'P':
                pointer_encoding = self.data[at]
                at += 1
                pointer_size = {0x03: 4, 0x0b: 4, 0x04: 8, 0x0c: 8}.get(pointer_encoding & 15)
                if pointer_size is None:
                    raise ValueError('CIE personality pointer encoding unsupported')
                at += pointer_size
            elif marker == 'L':
                at += 1
            elif marker == 'R':
                encoding = self.data[at]
                at += 1
        if at != augmentation_end or encoding != 0x1b:
            raise ValueError('CIE FDE encoding unsupported')
        relative, size = struct.unpack_from('<iI', self.data, fde_off + 8)
        function_rva = fde_rva + 8 + relative
        if function_rva != initial or not function_rva <= site_rva < function_rva + size:
            raise ValueError('FDE does not contain selected site')
        start = self.offset(function_rva, size)
        return {'start_rva': function_rva, 'end_rva_exclusive': function_rva + size,
            'start_file_offset': start, 'end_file_offset_exclusive': start + size, 'bytes': size,
            'fde_rva': fde_rva, 'fde_file_offset': fde_off, 'cie_file_offset': cie_off,
            'cie_augmentation': augmentation, 'fde_pointer_encoding': encoding,
            'code_alignment': code_align, 'data_alignment': data_align,
            'return_register': return_register, 'range_verified_from_existing_elf_unwind': True}


def parse_disassembly(path, elf, function):
    instructions = []
    for line in path.read_text(encoding='utf-8').splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)(.*?)\s*$', line)
        if match is None:
            continue
        address, raw, asm = int(match[1], 16), bytes.fromhex(match[2]), match[3].strip()
        if not asm:
            if not instructions or address != instructions[-1]['address'] + len(instructions[-1]['raw']):
                raise ValueError('Disassembly continuation is not contiguous')
            instructions[-1]['raw'] += raw
        else:
            instructions.append({'address': address, 'raw': raw, 'asm': asm})
    expected = function['start_rva']
    for item in instructions:
        if item['address'] != expected or len(item['raw']) > 15:
            raise ValueError('Disassembly instructions do not cover the exact function')
        off = elf.offset(item['address'], len(item['raw']))
        if elf.data[off:off + len(item['raw'])] != item['raw']:
            raise ValueError('Captured instruction bytes differ from pinned ELF')
        expected += len(item['raw'])
    if expected != function['end_rva_exclusive']:
        raise ValueError('Disassembly does not end at exact unwind function boundary')
    return instructions


def target_value(elf, target, asm, relocations):
    name, section = elf.section(target)
    value = {'rva': target, 'rva_hex': hex(target), 'section': name,
        'section_relative_offset': target - section['rva']}
    if target in relocations and relocations[target]['symbol']:
        value.update(kind='dynamic_symbol', identity=relocations[target])
    elif section['type'] == 8:
        value.update(kind='bss_field', identity={'section_relative_offset': target - section['rva']})
    elif asm.startswith('lea'):
        off = elf.offset(target)
        end = elf.data.find(b'\0', off, min(off + 4096, section['file_offset'] + section['bytes']))
        if end < 0:
            raise ValueError('Bounded full C string terminator unavailable')
        raw = elf.data[off:end + 1]
        value.update(kind='full_c_string', identity={'bytes': len(raw), 'sha256': sha(raw)},
            text=raw[:-1].decode('utf-8', errors='replace'), file_offset=off)
    else:
        width = next((size for word, size in [('XMMWORD', 16), ('QWORD', 8), ('DWORD', 4),
            ('WORD', 2), ('BYTE', 1)] if re.search(r'\b' + word + r'\b', asm)), None)
        if width is None:
            raise ValueError('Referenced numeric object width unresolved')
        off = elf.offset(target, width)
        raw = elf.data[off:off + width]
        value.update(kind='numeric_object', identity={'bytes': width, 'sha256': sha(raw)},
            value_hex=raw.hex(), file_offset=off)
    return value


def instruction_review(old_elf, new_elf, old_function, new_function, paths):
    before = parse_disassembly(paths[0], old_elf, old_function)
    after = parse_disassembly(paths[1], new_elf, new_function)
    if len(before) != len(after):
        raise ValueError('Function instruction count changed')
    old_relocs, new_relocs = old_elf.relocation_names(), new_elf.relocation_names()
    old_norm, new_norm = bytearray(), bytearray()
    counts = {'instructions': len(before), 'raw_identical_instructions': 0,
        'changed_rip_disp32_instructions': 0, 'changed_rel32_call_instructions': 0,
        'unexpected_changes': 0}
    references, calls, unexpected = [], [], []
    for index, (a, b) in enumerate(zip(before, after)):
        relative = a['address'] - old_function['start_rva']
        if relative != b['address'] - new_function['start_rva'] or len(a['raw']) != len(b['raw']):
            raise ValueError('Instruction boundaries or relative offsets changed')
        x, y = bytearray(a['raw']), bytearray(b['raw'])
        a_asm, b_asm = a['asm'].split('#')[0].strip(), b['asm'].split('#')[0].strip()
        if x == y:
            counts['raw_identical_instructions'] += 1
        if '[rip' in a_asm or '[rip' in b_asm:
            comments = [re.search(r'#\s*([0-9a-f]+)', item['asm']) for item in (a, b)]
            if not all(comments):
                raise ValueError('RIP target is missing from captured disassembly')
            targets = [int(match[1], 16) for match in comments]
            offsets = []
            for item, target in zip((a, b), targets):
                matches = [at for at in range(len(item['raw']) - 3) if
                    item['address'] + len(item['raw']) + struct.unpack_from('<i', item['raw'], at)[0] == target]
                if len(matches) != 1:
                    raise ValueError('RIP displacement field is not uniquely identified')
                offsets.append(matches[0])
            if offsets[0] != offsets[1]:
                raise ValueError('RIP displacement field location changed')
            at = offsets[0]
            x[at:at + 4] = y[at:at + 4] = b'\0' * 4
            asm_pair = [re.sub(r'\[rip[+-]0x[0-9a-f]+\]', '[rip+REL]', text) for text in (a_asm, b_asm)]
            identity = [target_value(elf, target, text, reloc) for elf, target, text, reloc in
                zip((old_elf, new_elf), targets, (a_asm, b_asm), (old_relocs, new_relocs))]
            equivalent = identity[0]['kind'] == identity[1]['kind'] and identity[0]['identity'] == identity[1]['identity']
            references.append({'instruction_index': index, 'function_relative_offset': relative,
                'displacement_byte_offset': at, 'instruction': asm_pair[0], 'before': identity[0],
                'after': identity[1], 'target_identity_equivalent': equivalent})
            if a['raw'] != b['raw']:
                counts['changed_rip_disp32_instructions'] += 1
            if asm_pair[0] != asm_pair[1] or not equivalent:
                unexpected.append({'index': index, 'reason': 'RIP instruction/target identity changed', 'before': a['asm'], 'after': b['asm']})
        elif a['raw'][0] == 0xe8 and b['raw'][0] == 0xe8 and len(x) == len(y) == 5:
            targets = [item['address'] + 5 + struct.unpack_from('<i', item['raw'], 1)[0] for item in (a, b)]
            labels = [re.search(r'<([^>]+)>', item['asm']) for item in (a, b)]
            names = [match[1] if match else None for match in labels]
            imported = bool(names[0] and names[0].endswith('@plt') and names[0] == names[1])
            value = {'function_relative_offset': relative, 'old_target_rva': targets[0],
                'new_target_rva': targets[1], 'old_annotation': names[0], 'new_annotation': names[1],
                'same_plt_import': imported, 'target_shift_bytes': targets[1] - targets[0]}
            if not imported:
                helper_identity = []
                for elf, target in zip((old_elf, new_elf), targets):
                    helper = elf.unwind_range(target)
                    if helper['start_rva'] != target or helper['bytes'] > 65536:
                        raise ValueError('Direct helper target/range outside narrow bounds')
                    off = helper['start_file_offset']
                    helper_identity.append(dict(helper, sha256=sha(elf.data[off:off + helper['bytes']])))
                value['helper_functions'] = helper_identity
                value['helper_raw_byte_identical'] = helper_identity[0]['bytes'] == helper_identity[1]['bytes'] and helper_identity[0]['sha256'] == helper_identity[1]['sha256']
            calls.append(value)
            x[1:5] = y[1:5] = b'\0' * 4
            if a['raw'] != b['raw']:
                counts['changed_rel32_call_instructions'] += 1
        elif a['raw'] != b['raw']:
            unexpected.append({'index': index, 'reason': 'Non-relocation instruction bytes changed',
                'before': a['asm'], 'after': b['asm'], 'old_hex': a['raw'].hex(), 'new_hex': b['raw'].hex()})
        if x != y:
            unexpected.append({'index': index, 'reason': 'Bytes outside classified relocation fields changed'})
        old_norm.extend(x)
        new_norm.extend(y)
    counts['unexpected_changes'] = len(unexpected)
    pending_helpers = [item for item in calls if not item['same_plt_import'] and not item['helper_raw_byte_identical']]
    return {'counts': counts, 'old_normalized_sha256': sha(old_norm), 'new_normalized_sha256': sha(new_norm),
        'normalized_instruction_bytes_identical': old_norm == new_norm, 'unexpected_changes': unexpected,
        'literal_global_references': references, 'direct_calls': calls,
        'all_literal_global_target_identities_equivalent': all(x['target_identity_equivalent'] for x in references),
        'pending_nonidentical_direct_helper_targets': pending_helpers,
        'scope': 'Entire unwind-bound preflight function; each direct literal/global target and first-level direct helper byte range only.'}


