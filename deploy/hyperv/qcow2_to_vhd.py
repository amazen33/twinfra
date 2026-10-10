#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read a standalone QCOW2 image into a fixed VHD; never mounts or boots a disk.

Uses only Python's standard library. Format references: QEMU's QCOW2 specification
and Microsoft's Virtual Hard Disk Image Format (fixed disk footer). Unsupported
features fail closed. Convert-VHD subsequently produces the dynamic Hyper-V VHDX.
"""
import argparse
from pathlib import Path
import struct
import uuid
import zlib


def read_at(stream, offset, size):
    if offset < 0 or size < 0 or offset + size > stream.seek(0, 2):
        raise ValueError('QCOW2 offset outside verified image')
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('Truncated QCOW2')
    return data


def footer(size):
    sectors = min(size // 512, 65535 * 16 * 255)
    if sectors >= 65535 * 16 * 63:
        spt, heads = 255, 16
    else:
        spt = 17
        heads = max(4, (sectors // spt + 1023) // 1024)
        if heads > 16 or sectors // spt >= heads * 1024:
            spt, heads = 31, 16
        if sectors // spt >= heads * 1024:
            spt, heads = 63, 16
    cylinders = sectors // spt // heads
    result = bytearray(512)
    struct.pack_into('>8sIIQI4sI4sQQHBBII16sB', result, 0,
                     b'conectix', 2, 0x10000, 0xffffffffffffffff, 0,
                     b'TWIN', 0x10000, b'Wi2k', size, size,
                     cylinders, heads, spt, 2, 0, uuid.uuid4().bytes, 0)
    struct.pack_into('>I', result, 64, (~sum(result)) & 0xffffffff)
    return result


def convert(source, target):
    with Path(source).open('rb') as src:
        h = read_at(src, 0, 104)
        magic, version = struct.unpack_from('>II', h)
        backing, backing_size, bits, size, crypt, l1_count, l1_offset = struct.unpack_from('>QIIQIIQ', h, 8)
        if magic != 0x514649fb or version not in (2, 3):
            raise ValueError('Not supported QCOW2')
        if backing or backing_size or crypt or not 9 <= bits <= 21:
            raise ValueError('Backing files/encryption/unsupported clusters forbidden')
        if version == 3 and struct.unpack_from('>Q', h, 72)[0]:
            raise ValueError('Dirty/corrupt/extended/external/non-deflate features forbidden')
        if not size or size % 512 or size > 32 * 1024**3 or l1_count > 4194304:
            raise ValueError('Unexpected base image virtual size/table size')
        cluster = 1 << bits
        entries = cluster // 8
        if l1_count * entries * cluster < size or l1_offset % cluster:
            raise ValueError('Invalid L1 geometry')
        l1 = struct.unpack('>' + 'Q' * l1_count, read_at(src, l1_offset, l1_count * 8))
        offset_mask = ((1 << 56) - 1) & ~511
        with Path(target).open('xb') as dst:
            dst.truncate(size + 512)
            cached_index, l2 = -1, ()
            for guest in range(0, size, cluster):
                index = guest // cluster
                table_index = index // entries
                table_offset = l1[table_index] & offset_mask
                if not table_offset:
                    continue
                if table_offset % cluster:
                    raise ValueError('Unaligned L2 table')
                if table_index != cached_index:
                    l2 = struct.unpack('>' + 'Q' * entries, read_at(src, table_offset, cluster))
                    cached_index = table_index
                entry = l2[index % entries]
                if entry & (1 << 62):
                    count_bits = bits - 8
                    shift = 62 - count_bits
                    offset = entry & ((1 << shift) - 1)
                    length = (((entry >> shift) & ((1 << count_bits) - 1)) + 1) * 512 - offset % 512
                    decoder = zlib.decompressobj(-15)
                    data = decoder.decompress(read_at(src, offset, length), cluster + 1)
                    if len(data) != cluster or not decoder.eof:
                        raise ValueError('Invalid compressed cluster length')
                elif entry & 1 or not (entry & offset_mask):
                    continue
                else:
                    offset = entry & offset_mask
                    if offset % cluster:
                        raise ValueError('Unaligned data cluster')
                    data = read_at(src, offset, cluster)
                dst.seek(guest)
                dst.write(data[:min(cluster, size - guest)])
            dst.seek(size)
            dst.write(footer(size))
    return size


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    print(f'Converted verified QCOW2 to fixed VHD ({convert(args.source, args.target)} virtual bytes); no host mount')
