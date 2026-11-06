"""Portable QR PNG output: use qrcode's matrix, not an optional image backend.

Older shared Windows runtimes can import qrcode while qrcode.image.pil is
missing. Encoding a matrix directly also avoids a Pillow dependency here.
"""
from pathlib import Path
import struct
import zlib
import qrcode


def png_bytes(payload,box_size=10,border=4):
    if not isinstance(box_size,int) or not 1<=box_size<=64:raise ValueError('Invalid QR box size')
    if not isinstance(border,int) or border<4:raise ValueError('QR quiet zone must be at least four modules')
    code=qrcode.QRCode(box_size=box_size,border=border)
    code.add_data(payload);code.make(fit=True);matrix=code.get_matrix()
    size=len(matrix)*box_size
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    pixels=b''.join((b'\x00'+bytes(0 if cell else 255 for cell in row for _ in range(box_size)))*box_size for row in matrix)
    header=struct.pack('>IIBBBBB',size,size,8,0,0,0,0)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')


class _Png:
    def __init__(self,data):self.data=data
    def save(self,target,format=None):
        if format is not None and str(format).upper()!='PNG':raise ValueError('QR output supports PNG only')
        if hasattr(target,'write'):target.write(self.data)
        else:Path(target).write_bytes(self.data)


def make(payload,box_size=10,border=4):
    """PNG-only save-compatible replacement for qrcode.make at app call sites."""
    return _Png(png_bytes(payload,box_size,border))
