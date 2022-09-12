import os
import sys
import io
import struct
import bsdiff4

# Required for pyinstaller
def get_filename(relative_path):
    if os.path.exists(relative_path):
        filename = relative_path
    else:
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        filename = os.path.join(base_path, relative_path)
    return filename


class Byte:
    def getInt8(self, value):
        return struct.pack("<b", value)

    def getUInt8(self, value):
        return struct.pack("<B", value)

    def getInt16(self, value):
        return struct.pack("<h", value)

    def getUInt16(self, value):
        return struct.pack("<H", value)

    def getInt32(self, value):
        return struct.pack("<l", value)

    def getUInt32(self, value):
        return struct.pack("<L", value)

    def getInt64(self, value):
        return struct.pack("<q", value)

    def getUInt64(self, value):
        return struct.pack("<Q", value)

    def getFloat(self, value):
        return struct.pack("<f", value)

    def getDouble(self, value):
        return struct.pack("<d", value)

    def getStringUTF8(self, string):
        return string.encode() + b'\x00'

    def getString(self, string, nbytes=4, utf=None):
        tmp = string.encode()
        if string:
            tmp += b'\x00'
        for t in tmp:
            if t & 0x80:
                st = string.encode(encoding='UTF-16')[2:] + b'\x00\x00'
                size = self.getInt32(-int(len(st)/2))
                return size + st
        if nbytes == 4:
            return self.getInt32(len(tmp)) + tmp
        elif nbytes == 8:
            return self.getInt64(len(tmp)) + tmp
        else:
            sys.exit(f"Not setup for {nbytes} nbytes")

    def getSHA(self, sha):
        return sha.encode() + b'\x00'


class File(Byte):
    def __init__(self, data):
        self.data = None
        self.setData(data)
        self.vanilla = self.getData()
        self.isPatched = False

    def setData(self, data):
        self.size = len(data)
        self.data = io.BytesIO(data)

    def getData(self):
        return bytearray(self.data.getbuffer())

    def patchData(self, patch):
        data = bsdiff4.patch(bytes(self.vanilla), bytes(patch))
        self.setData(data)
        self.isPatched = True

    def getPatch(self, mod):
        return bsdiff4.diff(bytes(self.vanilla), bytes(mod))

    def tell(self):
        return self.data.tell()
        
    def readBytes(self, size=None):
        if size is None:
            return self.data.read()
        return self.data.read(size)

    def readString(self, size=None):
        if size is None:
            size = self.readInt32()
        if size < 0:
            s = self.readBytes(-size*2)
            return s.decode('utf-16')[:-1]
        if size > 0:
            s = self.readBytes(size)
            return s.decode('utf-8')[:-1]
        return ''

    def readInt(self, size, signed):
        return int.from_bytes(self.data.read(size), byteorder='little', signed=signed)

    def readInt8(self):
        return self.readInt(1, True)

    def readInt16(self):
        return self.readInt(2, True)

    def readInt32(self):
        return self.readInt(4, True)

    def readInt64(self):
        return self.readInt(8, True)

    def readUInt8(self):
        return self.readInt(1, False)

    def readUInt16(self):
        return self.readInt(2, False)

    def readUInt32(self):
        return self.readInt(4, False)

    def readUInt64(self):
        return self.readInt(8, False)

    def readFloat(self):
        return struct.unpack("<f", self.data.read(4))[0]

    def readDouble(self):
        return struct.unpack("<d", self.data.read(8))[0]

    def readSHA(self):
        sha = self.readBytes(0x20).decode()
        assert self.readUInt8() == 0
        return sha
