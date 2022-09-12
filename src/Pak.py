from Utility import Byte, File
import os
import hashlib
import sys
import zlib
import crcmod

MAGIC = 0x0b5a6f12e1


class Entry:
    def __init__(self, pak):
        self.pak = pak
        self.offsetEntry = self.pak.tell()
        self._initialize()

    def _initialize(self):
        self._isModded = False
        self._data = None
        self._sha = None
        self._extracted = False
        self._shaDecomp = None

        self.pak.data.seek(self.offsetEntry)
        self.flags = self.pak.readUInt32()
        self.isOffset32BitSafe = self.flags & (1 << 31) > 0
        self.isUncompSize32BitSafe = self.flags & (1 << 30) > 0
        self.isSize32BitSafe = self.flags & (1 << 29) > 0
        self.compMethodIdx = (self.flags >> 23) & 0x3F
        self.isEncrypted = self.flags & (1 << 22) > 0
        self.compBlkCnt = (self.flags >> 6) & 0xFFFF
        self.calcMaxCompBlkSize = (self.flags & 0x3F) < 0x3F

        self.maxCompBlkSize = self.getMaxCompBlkSize()
        self.offset = self.read32Or64(self.isOffset32BitSafe)
        self.uncompSize = self.read32Or64(self.isUncompSize32BitSafe)
        self.compSize = self.getCompSize()
        self.compBlkSizes = self.getCompBlkSizes()
        self.maxCompBlkSize = min(self.maxCompBlkSize, self.uncompSize)

    def reset(self):
        self._initialize()

    def getMaxCompBlkSize(self):
        if self.compBlkCnt == 0:
            return 0
        if self.calcMaxCompBlkSize:
            size = (self.flags & 0x3F) << 11
        else:
            size = self.pak.readUInt32()
        return size

    def getCompSize(self):
        if self.compMethodIdx:
            return self.read32Or64(self.isSize32BitSafe)
        return self.uncompSize

    def read32Or64(self, is32BitSafe):
        if is32BitSafe:
            return self.pak.readUInt32()
        return self.pak.readUInt64()

    def getCompBlkSizes(self):
        if self.compBlkCnt == 0:
            return []
        elif self.compBlkCnt == 1:
            return [self.compSize]
        sizes = []
        for _ in range(self.compBlkCnt):
            sizes.append(self.pak.readUInt32())
        return sizes

    def extract(self):
        assert not self._extracted, "Already extracted!"
        self.pak.data.seek(self.offset)
        assert self.pak.readUInt64() == 0
        assert self.pak.readUInt64() == self.compSize
        assert self.pak.readUInt64() == self.uncompSize
        assert self.pak.readUInt32() == self.compMethodIdx
        self._sha = self.pak.readBytes(20)
        assert self.pak.readUInt32() == self.compBlkCnt
        offsetBlocks = []
        for size in self.compBlkSizes:
            start = self.pak.readUInt64()
            end = self.pak.readUInt64()
            assert size == end - start
            offsetBlocks.append(start)
        assert self.pak.readInt8() == 0

        if self.compMethodIdx:
            self._data = bytearray([])
            assert self.pak.readUInt32() == self.maxCompBlkSize
            for offset, size in zip(offsetBlocks, self.compBlkSizes):
                assert self.pak.tell() == self.offset + offset
                tmp = self.pak.readBytes(size)
                self._data += zlib.decompress(tmp)
                # assert tmp == zlib.compress(zlib.decompress(tmp))
        else:
            assert self.compSize == self.uncompSize
            self._data = self.pak.readBytes(self.uncompSize)

        self._shaDecomp = hashlib.sha1(self._data).digest()
        self._isModded = False
        self._extracted = True

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, newData):
        sha = hashlib.sha1(newData).digest()
        self._isModded = sha != self._shaDecomp
        if self._isModded:
            self._data = newData
            self._shaDecomp = sha

    @data.deleter
    def data(self):
        self._data = None
        self._shaDecomp = None
        self._isModded = False

    @property
    def isModded(self):
        return self._isModded

    @property
    def extracted(self):
        return self._extracted

    def buildEntry(self):
        # Compress data if needed
        # Updating flags as I go
        base = 0
        size = 0x10000
        data = bytearray([])
        self.compBlkSizes = []
        if self.compMethodIdx > 0:
            while base < len(self._data):
                start = len(data)
                data += zlib.compress(self._data[base:base+size])
                base += size
                end = len(data)
                self.compBlkSizes.append(end - start)
            self.compBlkCnt = len(self.compBlkSizes)
        else:
            data = self._data
        self._sha = hashlib.sha1(data).digest()
        self.compSize = len(data)
        self.uncompSize = len(self._data)
        if self.compMethodIdx > 0:
            self.maxCompBlkSize = min(0x10000, self.uncompSize)
            self.calcMaxCompBlkSize = (self.maxCompBlkSize >> 11) << 11 == self.maxCompBlkSize
            assert self.compBlkCnt > 0
        else:
            self.calcMaxCompBlkSize = False
            self.compBlkCnt = 0
            assert len(self.compBlkSizes) == 0

        entry = bytearray([0]*8)
        entry += self.pak.getUInt64(self.compSize)
        entry += self.pak.getUInt64(self.uncompSize)
        entry += self.pak.getUInt32(self.compMethodIdx)
        entry += self._sha
        entry += self.pak.getUInt32(self.compBlkCnt)
        if self.compBlkCnt > 0:
            offset = len(entry) + 8*2*self.compBlkCnt + 5
            for size in self.compBlkSizes:
                entry += self.pak.getUInt64(offset)
                offset += size
                entry += self.pak.getUInt64(offset)
            entry += b'\x00'
            entry += self.pak.getUInt32(self.maxCompBlkSize)
        else:
            entry += b'\x00'
        entry += data
        return entry

    def buildEncoding(self):
        flagsOrig = hex(self.flags)

        self.flags = self.isOffset32BitSafe << 31 \
            | self.isUncompSize32BitSafe << 30 \
            | self.isSize32BitSafe << 29 \
            | self.compMethodIdx << 23 \
            | self.isEncrypted << 22 \
            | self.compBlkCnt << 6

        if self.calcMaxCompBlkSize:
            self.flags |= self.maxCompBlkSize >> 11
        elif self.compBlkCnt > 0:
            self.flags |= 0x3f

        arr = self.pak.getUInt32(self.flags)
        if self.compBlkCnt:
            if not self.calcMaxCompBlkSize:
                arr += self.pak.getUInt32(self.maxCompBlkSize)
                assert self.maxCompBlkSize < 0x10000

        if self.isOffset32BitSafe:
            arr += self.pak.getUInt32(self.offset)
        else:
            arr += self.pak.getUInt64(self.offset)

        if self.isUncompSize32BitSafe:
            arr += self.pak.getUInt32(self.uncompSize)
        else:
            arr += self.pak.getUInt64(self.uncompSize)

        if self.compMethodIdx > 0:
            if self.isSize32BitSafe:
                arr += self.pak.getUInt32(self.compSize)
            else:
                arr += self.pak.getUInt64(self.compSize)
        else:
            assert self.compSize == self.uncompSize

        if self.compBlkCnt > 1:
            for size in self.compBlkSizes:
                arr += self.pak.getUInt32(size)

        return arr


class Mod(Byte):
    def __init__(self):
        super().__init__()
        self.entryDict = {}  ## FOR MODDED ENTRY ONLY
        self.sizeEntryies = None
        self.pak = None
        self.mountpoint = None
        self.numModdedFiles = 0
        self.pakName = None
        self.crc32 = None
        self.offsetEncoding = None
        self.offsetPathHash = None
        self.startPathHash = None
        self.sizePathHash = None
        self.offsetDirIdx = None
        self.startDirIdx = None
        self.sizeDirIdx = None
        self.dirContents = {'/':[]}

    def addEntry(self, filename, entry):
        # assert entry.isModded
        self.entryDict[filename] = entry
        self.numModdedFiles += 1

    def _buildEntry(self):
        assert len(self.pak) == 0
        for entry in self.entryDict.values():
            entry.offset = len(self.pak)
            self.pak += entry.buildEntry()
        self.sizeEntries = len(self.pak)

    def _buildMountpoint(self):
        if self.numModdedFiles == 0:
            return
        assert len(self.pak) == self.sizeEntries
        filenames = iter(self.entryDict.keys())
        path = next(filenames).split('/')[:-1]
        for filename in filenames:
            tmp = filename.split('/')[:-1]
            i = 0
            for p, t in zip(path, tmp):
                if p != t: break
                i += 1
            path = path[:i]
        self.mountpoint = '/'.join(path) + '/'
        self.pak += self.getString(self.mountpoint)

    def _buildNumModdedFiles(self):
        assert len(self.entryDict) == self.numModdedFiles
        self.pak += self.getUInt32(self.numModdedFiles)

    def calcCRC32(self, arr):
        barr = bytearray([0]*len(arr)*4)
        if type(arr) == str:
            for i,a in enumerate(arr.lower()):
                barr[i*4] = ord(a)
        else:
            for i,a in enumerate(arr):
                barr[i*4] = a
        f = crcmod.mkCrcFun(0x104C11DB7, initCrc=0xFFFFFFFF, xorOut=0)
        return 0xFFFFFFFF - f(barr)

    def _buildCRC32(self, pakName):
        self.pakName = os.path.basename(pakName)
        self.crc32 = self.calcCRC32('../../../Newera/Content/Paks/' + self.pakName)
        self.pak += self.getUInt64(self.crc32)

    def _addBuffers(self):
        self.offsetPathHash = len(self.pak)
        self.pak += b'\x00' * (4 + 8*2 + 20)
        self.offsetDirIdx = len(self.pak)
        self.pak += b'\x00' * (4 + 8*2 + 20)

    def _buildEncoding(self):
        self.offsetEncoding = {}
        encoding = bytearray()
        for filename, entry in self.entryDict.items():
            self.offsetEncoding[filename] = len(encoding)
            encoding += entry.buildEncoding()
        self.pak += self.getUInt32(len(encoding))
        self.pak += encoding
        self.pak += b'\x00'*4

    def _patchFile(self, offset, start, size):
        arr = self.getUInt32(1)
        arr += self.getUInt64(start)
        arr += self.getUInt64(size)
        chunk = self.pak[start:start+size]
        arr += hashlib.sha1(chunk).digest()
        self.pak[offset:offset+len(arr)] = arr
        assert len(arr) == 4 + 8*2 + 20

    def calcHashFNV(self, filename):
        filename = filename.lower().encode('utf16')[2:]
        offset = 0xcbf29ce484222325
        prime = 0x00000100000001b3
        fnv = offset + self.crc32
        for f in filename:
            fnv ^= f
            fnv *= prime
            fnv &= 0xFFFFFFFFFFFFFFFF
        return fnv

    def _buildPathHash(self):
        self.startPathHash = len(self.pak)
        self.pak += self.getUInt32(self.numModdedFiles)
        for filename, entry in self.entryDict.items():
            f = filename.split(self.mountpoint)[1]
            fnv = self.calcHashFNV(f)
            self.pak += self.getUInt64(fnv)
            self.pak += self.getUInt32(self.offsetEncoding[filename])
        self.pak += b'\x00'*4
        self.sizePathHash = len(self.pak) - self.startPathHash
        self._patchFile(self.offsetPathHash, self.startPathHash, self.sizePathHash)

    def _buildDirIdx(self):
        self.startDirIdx = len(self.pak)

        # Organize the contents of each directory
        for filename, entry in self.entryDict.items():
            path = filename.split(self.mountpoint)[1].split('/')
            basename = path.pop()
            if path == []:
                self.dirContents['/'].append(basename)
            else:
                p = ''
                for pi in path:
                    p += pi + '/'
                    if p not in self.dirContents:
                        self.dirContents[p] = []
                self.dirContents[p].append(basename)

        # Build the directory data
        self.pak += self.getUInt32(len(self.dirContents))
        for directory in sorted(self.dirContents.keys()):
            fileList = self.dirContents[directory]
            self.pak += self.getString(directory)
            self.pak += self.getUInt32(len(fileList))
            directory = self.mountpoint + directory
            if directory[-2:] == '//':
                directory = directory[:-1]
            for basename in sorted(fileList):
                filename = directory + basename
                assert filename in self.offsetEncoding
                self.pak += self.getString(basename)
                self.pak += self.getUInt32(self.offsetEncoding[filename])

        self.sizeDirIdx = len(self.pak) - self.startDirIdx
        self._patchFile(self.offsetDirIdx, self.startDirIdx, self.sizeDirIdx)

    def _buildFooter(self):
        self.pak += b'\x00'*17
        self.pak += self.getUInt64(MAGIC)
        self.pak += self.getUInt64(self.sizeEntries)
        self.pak += self.getUInt64(self.startPathHash - self.sizeEntries)
        self.pak += hashlib.sha1(self.pak[self.sizeEntries:self.startPathHash]).digest()
        compTypes = bytearray([0]*0xa0)
        compTypes[:4] = b'Zlib'
        self.pak += compTypes

    def buildPak(self, pakName):
        self.pak = bytearray()
        if self.numModdedFiles:
            print(self.numModdedFiles, 'files modded. Building pak')
            self._buildEntry()
            self._buildMountpoint()
            self._buildNumModdedFiles()
            self._buildCRC32(pakName)
            self._addBuffers()
            self._buildEncoding()
            self._buildPathHash()
            self._buildDirIdx()
            self._buildFooter()
        return self.pak


class Pak(File):
    def __init__(self, filename):
        self.filename = filename
        self.data = open(filename, 'rb')

        # Check sha
        self.data.seek(-0xcc, 2)
        assert self.readUInt64() == MAGIC
        self.offsetIndex = self.readUInt64()
        self.sizeIndex = self.readUInt64()
        self.shaIndex = self.readBytes(20)
        self.checkSHA(self.shaIndex, self.offsetIndex, self.sizeIndex)

        # Compression types -- assumed Zlib only
        self.compressionTypes = bytearray(self.data.read())
        assert self.compressionTypes[:4] == b'Zlib'
        assert int.from_bytes(self.compressionTypes[4:], byteorder='little') == 0

        # Start indexing
        self.data.seek(self.offsetIndex)
        self.mountpoint = self.readString()
        self.numFiles = self.readUInt32()
        self.crc32PakName = self.readUInt64()

        assert self.readUInt32() == 1
        self.offsetPathHash = self.readUInt64()
        self.sizePathHash = self.readUInt64()
        self.shaPathHash = self.readBytes(20)
        self.checkSHA(self.shaPathHash, self.offsetPathHash, self.sizePathHash)

        assert self.readUInt32() == 1
        self.offsetFullDir = self.readUInt64()
        self.sizeFullDir = self.readUInt64()
        self.shaFullDir = self.readBytes(20)
        self.checkSHA(self.shaFullDir, self.offsetFullDir, self.sizeFullDir)

        # Encoded pak entries
        self.offsetPakEntries = self.data.tell()
        self.encodedPakEntries = self.parsePakEntries()
        assert self.readInt32() == 0  # Num of encrypted stuff?

        # Filenames
        self.offsetFilenames = self.data.tell()
        self.entryDict, self.basenameDict = self.parseFilenames()  # Dict of filenames pointing to entries

        # Other
        self._mod = Mod()

    def __del__(self):
        self.data.close()

    def clean(self):
        self._mod = Mod()
        for entry in self.entryDict.values():
            entry.reset()

    def parseFilenames(self):
        # Skip memfnv stuff
        assert self.readUInt32() == self.numFiles
        self.data.seek(12*self.numFiles, 1)

        # Make sure we're starting at the right place
        if self.readUInt32():
            self.data.seek(-4, 1)
        else: # Always seems to be zero for mods made with UnrealPak
            assert self.tell() == self.offsetFullDir # Not true for the vanilla pak; true for mods

        # Map each encoded area offset to a full filename
        encodedOffsetDict = {}
        while True:
            numDir = self.readUInt32()
            if numDir == 0: break
            for _ in range(numDir):
                directory = self.mountpoint + self.readString()
                numFiles = self.readUInt32()
                if directory[-2:] == '//':
                    directory = directory[:-1]
                for _ in range(numFiles):
                    filename = directory + self.readString()
                    offset = self.readUInt32()
                    if offset in encodedOffsetDict:
                        assert encodedOffsetDict[offset] == filename
                    encodedOffsetDict[offset] = filename
        assert len(encodedOffsetDict) == self.numFiles

        # Map filenames to their corresponding entry
        # Sort keys by offsets to ensure the encoded pak entry
        # is mapped to the correct filename
        entryDict = {}
        keys = sorted(encodedOffsetDict.keys())  ## IS DEFINITELY NECESSARY TO SORT BY OFFSETS!!!
        for i, key in enumerate(keys):
            filename = encodedOffsetDict[key]
            assert filename not in entryDict
            entryDict[filename] = self.encodedPakEntries[i]
        assert len(entryDict) == len(self.encodedPakEntries)
        assert len(entryDict) == self.numFiles

        # Map basenames to full filenames
        # Done for convenience when picking files to extract
        basenameDict = {}
        for filename in entryDict:
            basename = filename.split('/')[-1]
            if basename not in basenameDict:
                basenameDict[basename] = []
            basenameDict[basename].append(filename)

        return entryDict, basenameDict

    def parsePakEntries(self):
        assert self.data.tell() == self.offsetPakEntries
        pakEntriesSize = self.readUInt32()
        offsetEnd = self.offsetPakEntries + pakEntriesSize + 4
        entries = []
        while self.tell() < offsetEnd:
            entries.append(Entry(self))
        assert self.tell() == offsetEnd
        ## Sort entries by offsets -- doesn't seem necessary, but keeping just in case
        entries.sort(key=lambda x: x.offset)
        return entries

    def checkSHA(self, sha, offset, size):
        origOffset = self.data.tell()
        self.data.seek(offset)
        data = self.readBytes(size)
        assert sha == hashlib.sha1(data).digest()
        self.data.seek(origOffset)

    def getFullFilePath(self, filename):
        if filename in self.entryDict:
            return filename
        basename = filename.split('/')[-1]
        if basename not in self.basenameDict:
            sys.exit(f"Basename {basename} does not exist! Double check {filename}!")
        if len(self.basenameDict[basename]) == 1:
            return self.basenameDict[basename][0]
        test = [filename in f for f in self.basenameDict[basename]]
        if sum(test) == 1:
            idx = test.index(1)
            return self.basenameDict[basename][idx]
        names = '\n  '.join(self.basenameDict[basename])
        sys.exit(f"{filename} is not unique! Be more specific!\n " + names)

    def getDirContents(self, directory):
        filenames = []
        for filename in self.entryDict:
            if directory in filename:
                filenames.append(filename)
        return filenames

    def extractFile(self, filename):
        filename = self.getFullFilePath(filename)
        self.entryDict[filename].extract()
        return bytearray(self.entryDict[filename].data)

    def deleteFile(self, filename):
        del self.entryDict[filename].data

    def updateData(self, filename, data, force=False):
        filename = self.getFullFilePath(filename)
        self.entryDict[filename].data = data
        if self.entryDict[filename].isModded or force:
            self._mod.addEntry(filename, self.entryDict[filename])

    def buildPak(self, pakName):
        pak = self._mod.buildPak(pakName)
        if pak:
            print('Dumping pak to', pakName)
            with open(pakName, 'wb') as file:
                file.write(pak)
        else:
            print('No files were modded. No pak to dump!')    
