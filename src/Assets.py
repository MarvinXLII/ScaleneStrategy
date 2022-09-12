from Utility import Byte, File
from functools import partial
import sys
import os
import ast
import struct
from dataclasses import dataclass

class FloatProperty(Byte):
    def __init__(self, file):
        self.dataType = 'FloatProperty'
        assert file.readInt64() == 4
        file.data.seek(1, 1)
        self.value = file.readFloat()

    def build(self, uasset):
        tmp = self.getInt64(4)
        tmp += bytearray([0])
        tmp += self.getFloat(self.value)
        return tmp

    def __repr__(self):
        return str(self.value)

    def get(self):
        return self.value


class StrProperty(Byte):
    def __init__(self, file):
        self.dataType = 'StrProperty'
        size = file.readInt64()
        file.data.seek(1, 1)
        self.string = file.readString()

    def build(self, uasset):
        tmp = self.getString(self.string)
        size = len(tmp)
        return self.getInt64(size) + b'\x00' + tmp

    def __repr__(self):
        return self.string

    def get(self):
        return self.string

class EnumProperty(Byte):
    def __init__(self, file, uasset):
        self.dataType = 'EnumProperty'
        assert file.readInt64() == 8
        self.value0 = uasset.getName(file.readInt64())
        assert file.readInt8() == 0
        self.value = uasset.getName(file.readInt64())

    def build(self, uasset):
        tmp = self.getInt64(8)
        tmp += self.getInt64(uasset.getIndex(self.value0))
        tmp += bytearray([0])
        tmp += self.getInt64(uasset.getIndex(self.value))
        return tmp

    def __repr__(self):
        return self.value

    def get(self):
        return self.value


class BoolProperty(Byte):
    def __init__(self, file):
        self.dataType = 'BoolProperty'
        assert file.readInt64() == 0
        self.value = file.readInt8()
        file.data.seek(1, 1)

    def build(self, uasset):
        tmp = bytearray([0]*8)
        tmp += self.getInt8(self.value)
        tmp += bytearray([0])
        return tmp

    def __repr__(self):
        return 'True' if self.value else 'False'

    def get(self):
        return 'True' if self.value else 'False'


class NameProperty(Byte):
    def __init__(self, file, uasset):
        self.dataType = 'NameProperty'
        assert file.readInt64() == 8
        file.data.seek(1, 1)
        self.name = uasset.getName(file.readInt64())

    def build(self, uasset):
        tmp = self.getInt64(8)
        tmp += bytearray([0])
        tmp += self.getInt64(uasset.getIndex(self.name))
        return tmp

    def __repr__(self):
        return self.name

    def get(self):
        return self.name

class IntProperty(Byte):
    def __init__(self, file):
        self.dataType = 'IntProperty'
        assert file.readInt64() == 4
        file.data.seek(1, 1)
        self.value = file.readInt32()

    def build(self, uasset):
        tmp = self.getInt64(4)
        tmp += bytearray([0])
        tmp += self.getInt32(self.value)
        return tmp

    def __repr__(self):
        return str(self.value)

    def get(self):
        return self.value


class UInt32Property(Byte):
    def __init__(self, file):
        self.dataType = 'UInt32Property'
        assert file.readInt64() == 4
        file.data.seek(1, 1)
        self.value = file.readUInt32()

    def build(self, uasset):
        tmp = self.getInt64(4)
        tmp += bytearray([0])
        tmp += self.getUInt32(self.value)
        return tmp

    def __repr__(self):
        return str(self.value)

    def get(self):
        return self.value


class ByteProperty(Byte):
    def __init__(self, file):
        self.dataType = 'ByteProperty'
        self.size = file.readInt64()
        # assert file.readInt64() == 1
        self.value0 = file.readInt64()
        file.data.seek(1, 1)
        if self.size == 1:
            self.value = file.readInt8()
        elif self.size == 8:
            self.value = file.readInt64()
        else:
            sys.exit(f'ByteProperty not set up for byte size of {self.size}')

    def build(self, uasset):
        tmp = self.getInt64(self.size)
        tmp += self.getInt64(self.value0)
        tmp += bytearray([0])
        if self.size == 1:
            tmp += self.getInt8(self.value)
        elif self.size == 8:
            tmp += self.getInt64(self.value)
        return tmp

    def __repr__(self):
        return str(self.value)

    def get(self):
        return self.value


class SoftObjectProperty(Byte):
    def __init__(self, file):
        self.dataType = 'SoftObjectProperty'
        assert file.readInt64() == 0xc
        file.data.seek(1, 1)
        self.asset = file.data.read(0xc)

    def build(self, uasset):
        tmp = self.getInt64(0xc)
        tmp += bytearray([0])
        tmp += self.asset
        return tmp
        
    def __repr__(self):
        return f"{self.asset} (SoftObjectProperty)"

    def get(self):
        return f"{self.asset} (SoftObjectProperty)"

class ObjectProperty(Byte):
    def __init__(self, file, uasset):
        self.dataType = 'ObjectProperty'
        assert file.readUInt64() == 4
        file.data.seek(1, 1)
        self.value = file.readInt32()

    def build(self, uasset):
        tmp = self.getInt64(4)
        tmp += bytearray([0])
        tmp += self.getInt32(self.value)
        return tmp
        
    def __repr__(self):
        return f"{self.value}"

    def get(self):
        return f"{self.value}"

# Essentially an array of structs?
class MapProperty(Byte):
    def __init__(self, file, uasset, callbackLoad, callbackBuild):
        # self.none = uasset.getIndex('None')
        self.callbackBuild = callbackBuild
        self.uasset = uasset
        self.dataType = 'MapProperty'
        self.size = file.readUInt64()
        self.prop = uasset.getName(file.readUInt64())
        assert uasset.getName(file.readUInt64()) == 'StructProperty'
        assert file.readUInt8() == 0
        end = file.tell() + self.size
        assert file.readUInt32() == 0
        self.num = file.readUInt32()
        self.data = {}
        for i in range(self.num):
            if self.prop == 'EnumProperty':
                key = uasset.getName(file.readInt64())
            elif self.prop == 'IntProperty':
                key = file.readInt32()
            elif self.prop == 'NameProperty':
                key = uasset.getName(file.readInt64())
            else:
                sys.exit(f"loadTable MapProperty not setup for {self.dataType}")
            self.data[key] = callbackLoad()
        assert file.tell() == end

    def build(self, uasset):
        tmp2 = bytearray([0,0,0,0])
        tmp2 += uasset.getUInt32(self.num)
        for key, value in self.data.items():
            if self.prop == 'EnumProperty':
                tmp2 += uasset.getUInt64(uasset.getIndex(key))
            elif self.prop == 'IntProperty':
                tmp2 += uasset.getUInt32(key)
            elif self.prop == 'NameProperty':
                tmp2 += uasset.getUInt64(uasset.getIndex(key))
            else:
                sys.exit()
            tmp2 += self.callbackBuild(value)

        tmp = bytearray([])
        tmp += self.uasset.getUInt64(len(tmp2))
        tmp += self.uasset.getUInt64(uasset.getIndex(self.prop))
        tmp += self.uasset.getUInt64(uasset.getIndex('StructProperty'))
        tmp += bytearray([0])
        return tmp + tmp2

    def __repr__(self):
        return self.data
        # return 'MapProperty repr not yet written!'

    def get(self):
        return 'MapProperty get not yet written!'

# MonsterDataAsset: Include a bunch of floats I won't need to modify.
# Just lost struct as a bytearray
class StructProperty(Byte):
    def __init__(self, file, uasset, callbackLoad, callbackBuild):
        self.none = uasset.getIndex('None')
        self.callbackBuild = callbackBuild
        self.dataType = 'StructProperty'
        self.structSize = file.readInt64()
        self.structType = uasset.getName(file.readInt64())
        file.data.seek(17, 1)
        # self.structData = file.data.read(self.size)
        self.structureWorks = True
        if self.structType == 'Vector':
            assert self.structSize == 0xc
            self.x = file.readFloat()
            self.y = file.readFloat()
            self.z = file.readFloat()
        elif self.structType == 'IntVector':
            self.x = file.readInt32()
            self.y = file.readInt32()
            self.z = file.readInt32()
        elif self.structType == 'Vector2D':
            assert self.structSize == 0x8
            self.x = file.readInt32()
            self.y = file.readInt32()
        elif self.structType == 'LinearColor':
            self.r = file.readFloat()
            self.g = file.readFloat()
            self.b = file.readFloat()
            self.a = file.readFloat()
        elif self.structType == 'Guid':
            assert self.structSize == 0x10
            self.guid = file.readBytes(self.structSize)
        elif self.structType == 'SoftClassPath':
            assert self.structSize == 0xc
            self.scp = file.readBytes(self.structSize)
        elif self.structType == 'Rotator':
            assert self.structSize == 0xc
            self.rx = file.readFloat()
            self.ry = file.readFloat()
            self.rz = file.readFloat()
        else:
            start = file.tell()
            try:
                self.structData = callbackLoad()
            except:
                print('Structure failed for', self.structType)
                self.structureWorks = False
                file.data.seek(start)
                self.structData = file.readBytes(self.structSize)

    def build(self, uasset):
        if self.structType == 'Vector':
            tmp = self.getInt64(self.structSize)
            tmp += self.getInt64(uasset.getIndex(self.structType))
            tmp += bytearray([0]*17)
            tmp += self.getFloat(self.x)
            tmp += self.getFloat(self.y)
            tmp += self.getFloat(self.z)
            return tmp
        elif self.structType == 'IntVector':
            tmp = self.getInt64(self.structSize)
            tmp += self.getInt64(uasset.getIndex(self.structType))
            tmp += bytearray([0]*17)
            tmp += self.getInt32(self.x)
            tmp += self.getInt32(self.y)
            tmp += self.getInt32(self.z)
            return tmp
        elif self.structType == 'Vector2D':
            tmp = self.getInt64(self.structSize)
            tmp += self.getInt64(uasset.getIndex(self.structType))
            tmp += bytearray([0]*17)
            tmp += self.getInt32(self.x)
            tmp += self.getInt32(self.y)
            return tmp
        elif self.structType == 'LinearColor':
            tmp = self.getInt64(self.structSize)
            tmp += self.getInt64(uasset.getIndex(self.structType))
            tmp += bytearray([0]*17)
            tmp += self.getFloat(self.r)
            tmp += self.getFloat(self.g)
            tmp += self.getFloat(self.b)
            tmp += self.getFloat(self.a)
            return tmp
        elif self.structType == 'Guid':
            tmp = self.getInt64(self.structSize)
            tmp += self.getInt64(uasset.getIndex(self.structType))
            tmp += bytearray([0]*17)
            tmp += self.guid
            return tmp
        elif self.structType == 'SoftClassPath':
            tmp = self.getInt64(self.structSize)
            tmp += self.getInt64(uasset.getIndex(self.structType))
            tmp += bytearray([0]*17)
            tmp += self.scp
            return tmp
        elif self.structType == 'Rotator':
            tmp = self.getInt64(self.structSize)
            tmp += self.getInt64(uasset.getIndex(self.structType))
            tmp += bytearray([0]*17)
            tmp += self.getFloat(self.rx)
            tmp += self.getFloat(self.ry)
            tmp += self.getFloat(self.rz)
            return tmp
        elif not self.structureWorks:
            tmp = self.getInt64(self.structSize)
            tmp += self.getInt64(uasset.getIndex(self.structType))
            tmp += bytearray([0]*17)
            tmp += self.structData
            return tmp

        none = uasset.getIndex('None')
        tmp2 = self.callbackBuild(self.structData)
        tmp = self.getInt64(len(tmp2))
        tmp += self.getInt64(uasset.getIndex(self.structType))
        tmp += bytearray([0]*17)
        return tmp + tmp2

    def __repr__(self):
        if self.structType == 'Vector' or self.structType == 'IntVector':
            return f"{{'x': {self.x}, 'y': {self.y}, 'z': {self.z}}}"
        elif self.structType == 'Vector2D' or self.structType == 'IntVector':
            return f"{{'x': {self.x}, 'y': {self.y}}}"
        elif self.structType == 'LinearColor':
            return f"{{'r': {self.r}, 'g': {self.g}, 'b': {self.b}, 'a': {self.a}}}"
        elif self.structType == 'Guid':
            return str(self.guid.hex())
        elif self.structType == 'SoftClassPath':
            return str(self.scp.hex())
        elif self.structType == 'Rotator':
            return f"{{'rx': {self.rx}, 'ry': {self.ry}, 'rz': {self.rz}}}"
        return str(self.structData)

    def get(self):
        dic = {'Type': self.structType}
        if self.structType == 'Guid' or self.structType == 'SoftClassPath':
            dic['Struct'] = self.__repr__()
        else:
            dic['Struct'] = ast.literal_eval(self.__repr__())
        return dic


class TextProperty(Byte):
    def __init__(self, file):
        self.dataType = 'TextProperty'
        self.size = file.readInt64()
        file.data.seek(5, 1)
        if file.readInt8() == -1:
            assert file.readInt32() > 0
            file.data.seek(-4, 1)
            self.string = ''
        else:
            self.namespace_size = file.readInt32()
            self.namespace = file.readString(self.namespace_size)
            assert file.readInt32() == 0x21
            self.sha = file.readSHA()
            size = file.readInt32()
            self.string = file.readString(size)

    def build(self, uasset):
        tmp = bytearray([0]*4)
        if not self.string:
            tmp += bytearray([0xff])
            return self.getInt64(9) + bytearray([0]) + tmp

        tmp += bytearray([0])
        tmp += self.getString(self.namespace)
        tmp += self.getInt32(0x21)
        tmp += self.getSHA(self.sha)
        tmp += self.getString(self.string)

        size = len(tmp)
        return self.getInt64(size) + bytearray([0]) + tmp

    def __repr__(self):
        return self.string


class ArrayProperty(Byte):
    def __init__(self, file, uasset, callbackLoad, callbackBuild):
        self.none = uasset.getIndex('None')
        self.callbackBuild = callbackBuild
        self.dataType = 'ArrayProperty'
        self.size = file.readInt64()
        self.prop = uasset.getName(file.readInt64())
        file.data.seek(1, 1)
        num = file.readInt32()
        self.array = []

        if self.prop == 'ByteProperty':
            assert self.size == 4 + num, f"{self.__class__.__name__}: {self.prop}"
            self.array = file.readBytes(num)
            return

        if self.prop == 'IntProperty' or self.prop == 'ObjectProperty':
            assert self.size == 4 + 4*num, f"{self.__class__.__name__}: {self.prop}"
            for _ in range(num):
                self.array.append(file.readInt32())
            return

        if self.prop == 'EnumProperty' or self.prop == 'NameProperty':
            assert self.size == 4 + 8*num, f"{self.__class__.__name__}: {self.prop}"
            for _ in range(num):
                self.array.append(uasset.getName(file.readInt64()))
            return

        if self.prop == 'StructProperty':
            self.name = uasset.getName(file.readInt64())
            assert uasset.getName(file.readInt64()) == 'StructProperty', f"{self.__class__.__name__}: {self.prop}"
            self.structSize = file.readInt64()
            self.structType = uasset.getName(file.readInt64())
            file.data.seek(17, 1)
            if self.structType == 'IntVector':
                for _ in range(num):
                    x = file.readUInt32()
                    y = file.readUInt32()
                    z = file.readUInt32()
                    self.array.append((x, y, z))
            elif self.structType == 'Guid':
                for _ in range(num):
                    guid = file.readBytes(0x10)
                    self.array.append(guid)
            else:
                for _ in range(num):
                    self.array.append(callbackLoad())
            return

        sys.exit(f"Load array property does not allow for {self.prop} types!")

    def build(self, uasset):
        none = uasset.getIndex('None')
        tmp1 = self.getInt64(uasset.getIndex(self.prop))
        tmp1 += bytearray([0])

        tmp2 = self.getInt32(len(self.array))
        if self.prop == 'ByteProperty':
            tmp2 += self.array
        if self.prop == 'IntProperty' or self.prop == 'ObjectProperty':
            for ai in self.array:
                tmp2 += self.getInt32(ai)
        elif self.prop == 'EnumProperty' or self.prop == 'NameProperty':
            for ai in self.array:
                tmp2 += self.getInt64(uasset.getIndex(ai))
        elif self.prop == 'StructProperty':
            tmp2 += self.getInt64(uasset.getIndex(self.name))
            tmp2 += self.getInt64(uasset.getIndex('StructProperty'))
            tmp2 += self.getInt64(self.structSize)
            tmp2 += self.getInt64(uasset.getIndex(self.structType))
            tmp2 += bytearray([0]*17)
            if self.structType == 'IntVector':
                for x, y, z in self.array:
                    tmp2 += self.getInt32(x)
                    tmp2 += self.getInt32(y)
                    tmp2 += self.getInt32(z)
            elif self.structType == 'Guid':
                for guid in self.array:
                    tmp2 += guid
            else:
                for ai in self.array:
                    tmp2 += self.callbackBuild(ai)

        tmp = self.getInt64(len(tmp2))
        return tmp + tmp1 + tmp2

    def __repr__(self):
        return str(self.array)

    def get(self):
        return ast.literal_eval(self.__repr__())
        # return self.array


class DataTable(Byte):
    def __init__(self, obj):
        self.obj = obj
        self.uasset = self.obj.uasset
        self.uexp = self.obj.uexp
        self.offset = self.uexp.tell()
        assert self.uexp.readUInt32() == 0
        self.number = self.uexp.readUInt32()
        self.data = {}
        for _ in range(self.number):
            key = self.uasset.getName(self.uexp.readUInt64())
            self.data[key] = obj.loadEntry()

    def build(self):
        uexp = bytearray()
        uexp += self.getUInt32(0)
        uexp += self.getUInt32(self.number)
        none = self.getUInt64(self.uasset.getIndex('None'))
        for i, (key, value) in enumerate(self.data.items()):
            uexp += self.getUInt64(self.uasset.getIndex(key))
            for k, v in value.items():
                uexp += self.getUInt64(self.uasset.getIndex(k))
                uexp += self.getUInt64(self.uasset.getIndex(v.dataType))
                uexp += v.build(self.uasset)
            uexp += none
        return uexp


class Chunk_EXPORTS(Byte):
    def __init__(self, uasset):
        self.uasset = uasset
        self.p1 = uasset.readInt32() # class (e.g. DataTable, BlueprintGeneratedClass)
        self.p2 = uasset.readInt32() # CoreUObject used for Blueprint, iff BlueprintGeneratedClass
        self.p3 = uasset.readInt32() # Default class
        # self.p4 = uasset.readInt32()
        self.p4 = uasset.getName(uasset.readInt32()) # Name or number????
        self.p5 = uasset.getName(uasset.readUInt64()) # Name seems to be important here
        self.p6 = uasset.readUInt32()
        self.size = uasset.readInt64()
        self.offset = uasset.readUInt64() - uasset.size
        assert uasset.readUInt64() == 0
        assert uasset.readUInt64() == 0
        assert uasset.readUInt64() == 0
        assert uasset.readUInt64() == 0
        self.a1 = uasset.readUInt32() # ?
        self.a2 = uasset.readUInt32() # ?
        self.a3 = uasset.readUInt32() # Starting index for preloadDependency
        self.a4 = uasset.readUInt32() # sum(a4, a5, a6, a7) == number of preloadDependency used in this uexp chunk
        self.a5 = uasset.readUInt32()
        self.a6 = uasset.readUInt32()
        self.a7 = uasset.readUInt32()
        self.uexp1 = None
        self.uexp2 = None # e.g. DataTable stuff

        # Structure of uexp
        if self.p2 < 0:
            self.structure = self.uasset.imports[-self.p2].p4
        elif self.p1 < 0:
            self.structure = self.uasset.imports[-self.p1].p4
        else:
            self.structure = None

    def build(self, uassetSize):
        exp = bytearray()
        exp += self.getInt32(self.p1)
        exp += self.getInt32(self.p2)
        exp += self.getInt32(self.p3)
        exp += self.getInt32(self.uasset.getIndex(self.p4))
        exp += self.getInt64(self.uasset.getIndex(self.p5))
        exp += self.getInt32(self.p6)
        exp += self.getInt64(self.size)
        exp += self.getInt64(self.offset + uassetSize)
        exp += self.getInt64(0)
        exp += self.getInt64(0)
        exp += self.getInt64(0)
        exp += self.getInt64(0)
        exp += self.getUInt32(self.a1)
        exp += self.getUInt32(self.a2)
        exp += self.getUInt32(self.a3)
        exp += self.getUInt32(self.a4)
        exp += self.getUInt32(self.a5)
        exp += self.getUInt32(self.a6)
        exp += self.getUInt32(self.a7)
        return exp

    def buildUExp(self):
        uexp = bytearray()
        if self.uexp1 is not None:
            for key, value in self.uexp1.items():
                uexp += self.getUInt64(self.uasset.getIndex(key))
                uexp += self.getUInt64(self.uasset.getIndex(value.dataType))
                uexp += value.build(self.uasset)
        uexp += self.getUInt64(self.uasset.getIndex('None'))

        if self.uexp2 is not None:
            try:
                uexp += self.uexp2.build()
            except:
                assert type(self.uexp2) == bytearray or type(self.uexp2) == bytes
                uexp += self.uexp2

        return uexp


class Chunk_IMPORTS(File):
    def __init__(self, uasset):
        self.uasset = uasset
        self.p1 = uasset.getName(uasset.readUInt64())
        self.p2 = uasset.getName(uasset.readUInt64())
        self.p3 = uasset.readInt32()
        self.p4 = uasset.getName(uasset.readUInt64())

    def build(self):
        imp = bytearray()
        imp += self.getUInt64(self.uasset.getIndex(self.p1))
        imp += self.getUInt64(self.uasset.getIndex(self.p2))
        imp += self.getInt32(self.p3)
        imp += self.getUInt64(self.uasset.getIndex(self.p4))
        return imp

    def __repr__(self):
        return f"  {self.p1}\n  {self.p2}\n  {self.p3}\n  {self.p4}\n"


@dataclass
class Index(Byte):
    idx: int
    string: str
    id: bytearray

    def build(self):
        b = self.getString(self.string)
        b += self.id
        return b

    def get(self):
        return {
            'string': self.string,
            'id': self.id.hex(),
        }

    def __repr__(self):
        i = str(self.idx).rjust(5, ' ')
        h = struct.unpack('<H', struct.pack('>H', self.idx))[0]
        h = format(h, f'04x')
        idVal = int.from_bytes(self.id, byteorder='little')
        idVal = format(idVal, f'08x')
        return f"{i} 0x{h} 0x{idVal} {self.string}"


class UAsset(File):
    indexId = {}
    
    def __init__(self, data, uexpSize):
        super().__init__(data)
        self.skip = []

        self.data.seek(0)
        self.uexpSize = uexpSize
        
        # "Header" of uasset
        assert self.readUInt32() == 0x9e2a83c1
        assert self.readUInt32() == 0xfffffff9
        assert self.readUInt64() == 0
        assert self.readUInt64() == 0

        # Size of uasset/umap file
        self.dataSize = self.readUInt32()
        assert self.dataSize == self.size

        assert self.readString() == 'None'

        # Not sure what each bit means
        self.encoding = self.readUInt32()
        assert self.encoding in [0x80000000,0x80040000,0x80020000]

        # Stuff for indexing (n = number, o = offset)
        self.n_indexing = self.readUInt32()
        self.o_indexing = self.readUInt32()
        assert self.readUInt64() == 0

        # Counts and offsets
        self.n_exports = self.readUInt32()
        self.o_exports = self.readUInt32()
        self.n_imports = self.readUInt32()
        self.o_imports = self.readUInt32()
        self.o_depends = self.readUInt32()
        self.n_depends = self.n_exports
        assert self.readUInt64() == 0
        assert self.readUInt64() == 0

        # ID for the file
        self.guid = self.readBytes(0x10)

        # TBD (GenerationCount?)
        assert self.readUInt32() == 1

        # Repeats of stuff
        assert self.readUInt32() == self.n_exports
        assert self.readUInt32() == self.n_indexing

        assert self.readUInt64() == 0
        assert self.readUInt64() == 0
        assert self.readUInt64() == 0
        assert self.readUInt64() == 0
        assert self.readUInt32() == 0

        # More TBD stuff (u = unknown)
        self.u_tbd_4 = self.readUInt32()
        assert self.readUInt32() == 0

        # More counts and offsets
        self.o_assetRegData = self.readUInt32()
        self.o_bulkDataStart = self.readUInt64()
        assert self.o_bulkDataStart == self.size + self.uexpSize - 4
        assert self.readUInt64() == 0
        self.n_preloadDependency = self.readUInt32()
        self.o_preloadDependency = self.readUInt32()
        assert self.o_preloadDependency - self.o_assetRegData == 4

        # Indexing chunk
        assert self.tell() == self.o_indexing
        self.index = {}
        self.indexName = {}
        self.indexId = {}
        for i in range(self.n_indexing):
            string = self.readString()
            key = self.readBytes(4)
            idx = Index(i, string, key)
            self.index[i] = idx
            self.indexName[idx.string] = i
            if idx.string in UAsset.indexId:
                assert UAsset.indexId[idx.string] == idx.id
            else:
                UAsset.indexId[idx.string] = idx.id

        assert self.tell() == self.o_imports

        self.imports = {}
        for i in range(self.n_imports):
            self.imports[i+1] = Chunk_IMPORTS(self)
        assert self.tell() == self.o_exports

        self.exports = {}
        for i in range(self.n_exports):
            self.exports[i+1] = Chunk_EXPORTS(self)
        assert self.tell() == self.o_depends

        self.depends = {}
        for i in range(self.n_depends):
            self.depends[i+1] = self.readInt32()
            assert self.depends[i+1] == 0
        assert self.tell() == self.o_assetRegData

        self.assetRegData = self.readUInt32()
        assert self.assetRegData == 0

        self.preloadDependency = {}
        for i in range(self.n_preloadDependency):
            self.preloadDependency[i] = self.readInt32()
        assert self.tell() == self.size

    def build(self, uexpSize):
        # First build indexing
        indexing = bytearray()
        for i in range(self.n_indexing):
            indexing += self.index[i].build()
        
        # Next must calculate size of uasset (assumes nothing else will change in size!)
        size = self.o_indexing + len(indexing) + 0x1c*self.n_imports \
            + 0x68*self.n_exports + 4*self.n_depends + 4 + 4*self.n_preloadDependency

        uasset = bytearray()
        def updateOffset(addr):
            assert addr > 0
            uasset[addr:addr+4] = self.getUInt32(len(uasset))
        
        offsets = [0]*7
        uasset += self.getUInt32(0x9e2a83c1)
        uasset += self.getUInt32(0xfffffff9)
        uasset += self.getUInt64(0)
        uasset += self.getUInt64(0)
        uasset += self.getUInt32(size)
        uasset += self.getString('None')
        uasset += self.getUInt32(self.encoding)
        uasset += self.getUInt32(self.n_indexing)
        offsets[0] = len(uasset)
        uasset += self.getUInt32(self.o_indexing)
        uasset += self.getUInt64(0)
        uasset += self.getUInt32(self.n_exports)
        offsets[1] = len(uasset)
        uasset += self.getUInt32(self.o_exports)
        uasset += self.getUInt32(self.n_imports)
        offsets[2] = len(uasset)
        uasset += self.getUInt32(self.o_imports)
        offsets[3] = len(uasset)
        uasset += self.getUInt32(self.o_depends)
        uasset += self.getUInt64(0)
        uasset += self.getUInt64(0)
        uasset += self.guid
        uasset += self.getUInt32(1)
        uasset += self.getUInt32(self.n_exports)
        uasset += self.getUInt32(self.n_indexing)
        uasset += self.getUInt64(0)
        uasset += self.getUInt64(0)
        uasset += self.getUInt64(0)
        uasset += self.getUInt64(0)
        uasset += self.getUInt32(0)
        uasset += self.getUInt32(self.u_tbd_4)
        uasset += self.getUInt32(0)
        offsets[5] = len(uasset)
        uasset += self.getUInt32(self.o_assetRegData)
        uasset += self.getUInt64(size + uexpSize - 4)
        uasset += self.getUInt64(0)
        uasset += self.getUInt32(self.n_preloadDependency)
        offsets[6] = len(uasset)
        uasset += self.getUInt32(self.o_preloadDependency)
        updateOffset(offsets[0])
        uasset += indexing
        updateOffset(offsets[2])
        for imp in self.imports.values():
            uasset += imp.build()
        updateOffset(offsets[1])
        for exp in self.exports.values():
            uasset += exp.build(size)
        updateOffset(offsets[3])
        for dep in self.depends.values():
            uasset += self.getInt32(dep)
        updateOffset(offsets[5])
        uasset += self.getUInt32(0)
        updateOffset(offsets[6])
        for dep in self.preloadDependency.values():
            uasset += self.getInt32(dep)

        assert len(uasset) == size
        return uasset

    # TODO: account for changes in size of old and new entries
    def replaceIndices(self, newIndices):

        # First, clear out the indices to be overwritten and store the keys to be used
        keyDict = {}
        for default, new in newIndices.items():
            keyDict[default] = self.getIndex(default)
            assert keyDict[default] < 0xFFFFFFFF
            del self.indexName[default]

        # Add all the new indices
        for default, new in newIndices.items():
            idx = keyDict[default]
            id = UAsset.indexId[new]
            self.indexName[new] = idx
            self.index[idx] = Index(idx, new, id)

    def getName(self, value):
        name = self.index[value & 0xffffffff].string
        value >>= 32
        if value:
            return f"{name}_{value-1}"
        return name

    # A lot of files have unnecessary indices,
    # e.g. BATTLE_WEAPON_ENEMY_N_206 and BATTLE_WEAPON_ENEMY_N
    # Priority goes towards the latter
    def getIndex(self, name):
        if name in self.indexName:
            idx1 = self.indexName[name]
        else:
            idx1 = -1

        n = name.split('_')
        v = n.pop()
        if v.isnumeric() and (v[0] != '0' or len(v) == 1):
            idx2 = int(v) + 1 << 32
            b = '_'.join(n)
            idx2 += self.indexName[b]
        else:
            idx2 = -1

        idx = max(idx1, idx2)
        if idx >= 0:
            return idx

        assert name in UAsset.indexId
        self.addIndex(name)
        return self.indexName[name]

    def addIndex(self, name):
        if name in self.indexName:
            assert name in UAsset.indexId
            return
        # Test the full name first
        if name not in UAsset.indexId:
            # Test the basename
            index = self.getIndex(name)
            basename = self.getName(index & 0xFFFFFFFF)
            if basename not in UAsset.indexId:
                sys.exit(f"{name} is not in UAsset.indexId yet!")
            # Use the basename instead of the full name
            name = basename
        # Add new index to uasset
        i = len(self.index)
        self.index[i] = Index(i, name, UAsset.indexId[name])
        self.indexName[name] = i
        self.n_indexing += 1

    def skipEntry(self, name):
        self.skip.append(name)


# NB: This is written specifically for the files used.
class Data:
    def __init__(self, pak, filename):
        self.pak = pak
        self.filename = filename
        if '.umap' in self.filename:
            self.filename_uexp = self.filename.replace('umap', 'uexp')
        elif '.uasset' in self.filename:
            self.filename_uexp = self.filename.replace('uasset', 'uexp')
        # Load data
        print(f'Loading data from {filename}')
        self.uexp = File(self.pak.extractFile(self.filename_uexp))
        self.uasset = UAsset(self.pak.extractFile(self.filename), self.uexp.size)
        # Store none index
        self.none = self.uasset.getIndex('None')
        # Organize/"parse" uexp data
        self.setSwitcher()
        self.parseUExp()

    def setSwitcher(self):
        self.switcher = {  # REPLACE WITH MATCH IN py3.10????
            'EnumProperty': partial(EnumProperty, self.uexp, self.uasset),
            'TextProperty': partial(TextProperty, self.uexp),
            'IntProperty': partial(IntProperty, self.uexp),
            'UInt32Property': partial(UInt32Property, self.uexp),
            'ArrayProperty': partial(ArrayProperty, self.uexp, self.uasset, self.loadEntry, self.buildEntry),
            'StrProperty': partial(StrProperty, self.uexp),
            'BoolProperty': partial(BoolProperty, self.uexp),
            'NameProperty': partial(NameProperty, self.uexp, self.uasset),
            'StructProperty': partial(StructProperty, self.uexp, self.uasset, self.loadEntry, self.buildEntry),
            'FloatProperty': partial(FloatProperty, self.uexp),
            'ByteProperty': partial(ByteProperty, self.uexp),
            'SoftObjectProperty': partial(SoftObjectProperty, self.uexp),
            'ObjectProperty': partial(ObjectProperty, self.uexp, self.uasset),
            'MapProperty': partial(MapProperty, self.uexp, self.uasset, self.loadEntry, self.buildEntry),
        }

    def parseUExp(self):
        self.uexp.data.seek(0)
        for exp in self.uasset.exports.values():
            assert self.uexp.tell() == exp.offset
            end = exp.offset + exp.size

            dic = self.loadEntry()
            assert self.uexp.tell() <= end

            # Store dict
            if dic:
                exp.uexp1 = dic

            if exp.structure == 'DataTable':
                exp.uexp2 = DataTable(self)
            else:
                size = end - self.uexp.tell()
                if size > 0:
                    exp.uexp2 = self.uexp.readBytes(size)

            assert self.uexp.tell() == end

        # Make sure uexp is at the end of the file
        assert self.uexp.readUInt32() == 0x9e2a83c1

    def getDataTable(self):
        assert self.uasset.n_exports == 1
        assert self.uasset.exports[1].structure == 'DataTable'
        return self.uasset.exports[1].uexp2.data

    def getCommand(self, command):
        objs = {}
        for k, exp in self.uasset.exports.items():
            if exp.structure == command:
                objs[k] = exp.uexp1
        return objs

    def getUExp1Obj(self, idx):
        return self.uasset.exports[idx].uexp1

    def build(self):

        # Build uexp, storing all offsets and sizes for the start of each chunk
        # Important to store these in case anything changes (e.g. strings!)
        newUExp = bytearray()
        for exp in self.uasset.exports.values():
            exp.offset = len(newUExp)
            newUExp += exp.buildUExp()
            exp.size = len(newUExp) - exp.offset
        newUExp += self.uexp.getUInt32(0x9e2a83c1)

        newUAsset = self.uasset.build(len(newUExp))
        return newUAsset, newUExp

    def loadEntry(self):
        dic = {}
        nextValue = self.uexp.readUInt64()
        while nextValue != self.none:
            key = self.uasset.getName(nextValue)
            prop = self.uasset.getName(self.uexp.readUInt64())
            assert prop in self.switcher, f"{prop} not in switcher"
            dic[key] = self.switcher[prop]()
            nextValue = self.uexp.readUInt64()
        return dic

    def buildEntry(self, entry):
        data = bytearray()
        for key, d in entry.items():
            data += self.uexp.getInt64(self.uasset.getIndex(key))
            data += self.uexp.getInt64(self.uasset.getIndex(d.dataType))
            data += d.build(self.uasset)
        data += self.uexp.getInt64(self.none)
        return data

    def update(self, force=False):
        # Build and set data
        uasset, uexp = self.build()
        self.uasset.setData(uasset)
        self.uexp.setData(uexp)
        # Patch pak
        self.pak.updateData(self.filename, uasset, force=force)
        self.pak.updateData(self.filename_uexp, uexp, force=force)
