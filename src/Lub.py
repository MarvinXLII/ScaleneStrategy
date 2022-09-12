from Utility import File, get_filename
from dataclasses import dataclass
from more_itertools import peekable
import sys
import os
from copy import deepcopy

class Instruction:
    def __init__(self):
        self.name = None
        self.A = None
        self.B = None
        self.C = None

    def __repr__(self):
        C = '_' if self.C is None else self.C
        return f'{self.name} : {self.A} {self.B} {C}'

class ABC(Instruction):
    def __init__(self, name, value):
        self.name = name
        self.opcode = value & 0x3F
        value >>= 6
        self.A = value & 0xFF
        value >>= 8
        self.C = value & 0x1FF
        value >>= 9
        self.B = value & 0x1FF

    def to_value(self):
        value = self.B
        value <<= 9
        value += self.C
        value <<= 8
        value += self.A
        value <<= 6
        value += self.opcode
        return value
        
class ABx(Instruction):
    def __init__(self, name, value):
        self.name = name
        self.opcode = value & 0x3F
        value >>= 6
        self.A = value & 0xFF
        value >>= 8
        self.B = value
        self.C = None

    def to_value(self):
        value = self.B
        value <<= 8
        value += self.A
        value <<= 6
        value += self.opcode
        return value

class AsBx(Instruction):
    def __init__(self, name, value):
        self.name = name
        self.opcode = value & 0x3F
        value >>= 6
        self.A = value & 0xFF
        value >>= 8
        self.B = value - 0x1FFFF
        self.C = None
        
    def to_value(self):
        value = self.B + 0x1FFFF
        value <<= 8
        value += self.A
        value <<= 6
        value += self.opcode
        return value
        

@dataclass
class InstrTypes:
    name: str
    type: str
    doc: str = ""

    def GetInstruction(self, value):
        if self.type == 'ABC':
            instr = ABC(self.name, value)
        elif self.type == 'ABx':
            instr = ABx(self.name, value)
        elif self.type == 'AsBx':
            instr = AsBx(self.name, value)
        else:
            sys.exit(f'{self.name} is not a type!')
        instr.__doc__ = self.doc
        return instr
    

opcodeList = [
    # 0
    InstrTypes('MOVE', 'ABC', 'Copy a value between registers'),
    InstrTypes('LOADK', 'ABx', 'Load a constant into a register'),
    InstrTypes('LOADBOOL', 'ABC', 'Load a boolean into a register'),
    InstrTypes('LOADNIL', 'ABC', 'Load nil values into a range of registers'),
    InstrTypes('GETUPVAL', 'ABC', 'Read an upvalue into a register'),
    # 5
    InstrTypes('GETGLOBAL', 'ABx', 'Read a global variable into a register'),
    InstrTypes('GETTABLE', 'ABC', 'Read a table element into a register'),
    InstrTypes('SETGLOBAL', 'ABx', 'Write a register value into a global variable'),
    InstrTypes('SETUPVAL', 'ABC', 'Write a register value into an upvalue'),
    InstrTypes('SETTABLE', 'ABC', 'Write a register value into a table element'),
    # 10
    InstrTypes('NEWTABLE', 'ABC', 'Create a new table'),
    InstrTypes('SELF', 'ABC', 'Prepare an object method for calling'),
    InstrTypes('ADD', 'ABC', 'Addition operator'),
    InstrTypes('SUB', 'ABC', 'Subtraction operator'),
    InstrTypes('MUL', 'ABC', 'Multiplication operator'),
    # 15
    InstrTypes('DIV', 'ABC', 'Division operator'),
    InstrTypes('MOD', 'ABC', 'Modulus (remainder) operator'),
    InstrTypes('POW', 'ABC', 'Exponentiation operator'),
    InstrTypes('UNM', 'ABC', 'Unary minus operator'),
    InstrTypes('NOT', 'ABC', 'Logical NOT operator'),
    # 20
    InstrTypes('LEN', 'ABC', 'Length operator'),
    InstrTypes('CONCAT', 'ABC', 'Concatenate a range of registers'),
    InstrTypes('JMP', 'AsBx', 'Unconditional jump'),
    InstrTypes('EQ', 'ABC', 'Equality test'),
    InstrTypes('LT', 'ABC', 'Less than test'),
    # 25
    InstrTypes('LE', 'ABC', 'Less than or equal to test'),
    InstrTypes('TEST', 'ABC', 'Boolean test, with conditional jump'),
    InstrTypes('TESTSET', 'ABC', 'Boolean test, with conditional jump and assignment'),
    InstrTypes('CALL', 'ABC', 'Call a closure'),
    InstrTypes('TAILCALL', 'ABC', 'Perform a tail call'),
    # 30
    InstrTypes('RETURN', 'ABC', 'Return from function call'),
    InstrTypes('FORLOOP', 'AsBx', 'Iterate a numeric for loop'),
    InstrTypes('FORPREP', 'AsBx', 'Initialization for a numeric for loop'),
    InstrTypes('TFORLOOP', 'ABC', 'Iterate a generic for loop'),
    InstrTypes('SETLIST', 'ABC', 'Set a range of array elements for a table'),
    # 35
    InstrTypes('CLOSE', 'ABC', 'Close a range of locals being used as upvalues'),
    InstrTypes('CLOSURE', 'ABx', 'Create a closure of a function prototype'),
    InstrTypes('VARARG', 'ABC', 'Assign vararg function arguments to registers'),
]

opcodeDict = {i.name:i for i in opcodeList}
    


class Chunk:
    def __init__(self, lub, proto=None):
        if proto is None:
            proto = 0
        self.lub = lub
        self.offset = self.lub.tell()
        
        size = self.lub.readUInt64()
        self.sourceName = self.lub.readString(size)
        self.firstLine = self.lub.readUInt32()
        self.lastLine = self.lub.readUInt32()
        self.numUpVal = self.lub.readUInt8()
        self.numParam = self.lub.readUInt8()
        self.isVarArgFlag = self.lub.readUInt8()
        if self.isVarArgFlag == 0:
            self.varArg = None
        else:
            self.hasArg = self.isVarArgFlag & 0x1
            self.isVarArg = self.isVarArgFlag & 0x2
            self.needsArg = self.isVarArgFlag & 0x4
        self.maxStackSize = self.lub.readUInt8()


        self.sizeCode = self.lub.readUInt32()
        self.instrList = []
        for _ in range(self.sizeCode):
            instr = self.loadInstr()
            self.instrList.append(instr)

        # List of constants
        self.sizeConst = self.lub.readUInt32()
        self.constList = []
        self.constIdx = {}
        for i in range(self.sizeConst):
            t = self.lub.readUInt8()
            if t == 0: # LUA_TNIL
                value = None
            elif t == 1: # LUA_BOOLEAN
                b = self.lub.readUInt8()
                assert b == 0 or b == 1
                value = 'BoolTrue' if b == 1 else 'BoolFalse'
            elif t == 3: # LUA_NUMBER
                value = self.lub.readDouble()
            elif t == 4: # LUA_STRING
                size = self.lub.readUInt64()
                value = self.lub.readString(size)
            self.constList.append(value)
            assert value not in self.constIdx, f"{value} already in constIdx: {list(self.constIdx.keys())}"
            self.constIdx[value] = i

        self.sizeProto = self.lub.readUInt32()
        self.protoList = []
        for i in range(self.sizeProto):
            self.protoList.append(Chunk(self.lub, proto=proto+1))
        
        # Source line positions (optional debug data)
        self.sizePositions = self.lub.readUInt32()
        self.lineList = []
        for _ in range(self.sizePositions):
            self.lineList.append(self.lub.readUInt32())
        
        # List of locals (optional debug data)
        self.sizeLocals = self.lub.readUInt32()
        self.localList = []
        self.localIdx = {}
        for i in range(self.sizeLocals):
            size = self.lub.readUInt64()
            varname = self.lub.readString(size)
            startpc = self.lub.readUInt32()
            endpc = self.lub.readUInt32()
            self.localList.append((varname, startpc, endpc))
            # self.localList.append(varname)
            # assert endpc + 1 == len(self.instrList)
            # assert varname not in self.localIdx   ### CAN APPEAR MULTIPLE TIMES!!!
            self.localIdx[varname] = i
        
        # List of upvalues (optional debug data)
        self.sizeUpVals = self.lub.readUInt32()
        # assert self.sizeUpVals == 0
        self.upValList = []
        for _ in range(self.sizeUpVals):
            size = self.lub.readUInt64()
            string = self.lub.readString(size)
            self.upValList.append(string)

    # Stores tables and calls in an accessible manner
    def organize(self):

        # Setup localStart for start and end
        localStart = [i for _,i,_ in self.localList]
        localEnd = [i for _,_,i in self.localList]
        localReg = 0
        localIdx = 0
        reg = {}

        # Split up ListInstr to functions, tables, etc.
        # Done so sets of instructions can be updated and strung together
        self.instructions = []
        self.instrTables = {}
        self.instrFunctions = {}

        # Goal is just to group instructions
        def getNum(x):
            e = x >> 3
            if e > 0:
                m = (x & 0b0111) + 0b1000
                return m * 2 ** (e - 1)
            return x

        # TODO: cleanup!!!!!
        funcNameDict = {}
        i = 0
        instrList = list(self.instrList)
        while instrList:
            instr = instrList.pop(0)
            i += 1
            
            def countInstr(i, n=0):
                for j in i:
                    if type(j) == list:
                        n += countInstr(j)
                    else:
                        n += 1
                return n
            n = countInstr(self.instructions)

            if instr.name == 'NEWTABLE' and \
               ((instr.B > 0 and instr.C == 0) or \
                (instr.B == 0 and instr.C > 0)): # SKIP TABLES OF ARBITRARY SIZE OR USE MIX OF B AND C
                instrList.insert(0, instr)
                table = Table(self, instrList) # NOT SETUP FOR TABLES OF ARBITRARY SIZE
                lst = table.instrList
                i += len(lst)-1

                # Store the instructions
                self.instructions.append(lst)

                # Get the table name (if it exists) and store it
                for j in range(localIdx):
                    if i >= localEnd[j]:
                        localEnd[j] = len(self.instrList)
                        localReg -= 1

                while localStart and i >= localStart[0]:
                    line = localStart.pop(0)
                    reg[localReg] = self.localList[localIdx][0]
                    localReg += 1
                    localIdx += 1

                if instr.A in reg:
                    tableName = reg[instr.A]
                elif instrList[0].name == 'SETGLOBAL':
                    _instr = instrList[0]
                    assert _instr.B < 0x100
                    tableName = self.constList[_instr.B]
                else:
                    tableName = '----'

                if tableName not in self.instrTables:
                    self.instrTables[tableName] = []
                self.instrTables[tableName].append(table)

                # Continue to the next loop
                continue

            if instr.name == 'CALL' and instr.B > 0:
                regA = instr.A
                lst = [instr]
                usePrevFunc = False
                while True:
                    _instr = self.instructions.pop()
                    lst.append(_instr)
                    if isinstance(_instr, Instruction):
                        if _instr.A == instr.A:
                            break
                    elif isinstance(_instr, Function):
                        ### VERY CRUDE FIX! DO THIS PROPERLY!!!!
                        # ms05_x06_research_01_change_map.lub
                        # require returns function that gets executed
                        # doesn't reach instr.A, getting function instead
                        self.instructions.append(_instr)
                        usePrevFunc = True
                        lst.pop()
                        break
                    elif isinstance(_instr, Table):
                        pass
                        # if _instr.A == Table.instrList[0].A:
                        #     break

                if usePrevFunc:
                    pass
                elif _instr.name == 'GETGLOBAL':
                    funcName = self.constList[_instr.B]
                else:
                    funcName = '----'
                # funcNameDict[regA] = funcName
                
                if funcName not in self.instrFunctions:
                    self.instrFunctions[funcName] = []
                func = Function(self, lst[::-1])
                self.instrFunctions[funcName].append(func)
                self.instructions.append(func)
                continue

            self.instructions.append(instr)

    def addConst(self, value):
        if not self.hasConst(value):
            self.constList.append(value)
            self.constIdx[value] = len(self.constList) - 1
            self.sizeConst += 1

    def hasConst(self, value):
        return value in self.constIdx

    def getConstIdx(self, value):
        if value not in self.constIdx:
            self.addConst(value)
        return self.constIdx[value]

    def getConst(self, index):
        return self.constList[index]

    def hasLocal(self, value):
        return value in self.localIdx

    def getLocalIdx(self, value):
        if value not in self.localIdx:
            self.addLocal(value)
        return self.localIdx[value]

    def getLocal(self, index):
        return self.localList[index]

    def loadInstr(self):
        value = self.lub.readUInt32()
        opcode = value & 0x3F
        return opcodeList[opcode].GetInstruction(value)

    def build(self, vanilla, buffer=None):
        if buffer is None:
            buffer = bytearray()

        # buffer += self.lub.getString(self.sourceName, nbytes=8)
        buffer += self.lub.getString('', nbytes=8)
        buffer += self.lub.getUInt32(self.firstLine)
        buffer += self.lub.getUInt32(self.lastLine)
        buffer += self.lub.getUInt8(self.numUpVal)
        buffer += self.lub.getUInt8(self.numParam)
        buffer += self.lub.getUInt8(self.isVarArgFlag)
        buffer += self.lub.getUInt8(self.maxStackSize)

        # Instructions
        def appendList(lst, instrList=None):
            if instrList is None:
                instrList = []
            for li in lst:
                if type(li) == list:
                    appendList(li, instrList)
                elif isinstance(li, Function):
                    appendList(li.getInstructions(), instrList)
                elif isinstance(li, Table):
                    appendList(li.getInstructions(), instrList)
                else:
                    instrList.append(li)
            return instrList
        instrList = appendList(self.instructions)

        buffer += self.lub.getUInt32(len(instrList))
        for instr in instrList:
            buffer += self.lub.getUInt32(instr.to_value())

        # Constants
        buffer += self.lub.getUInt32(self.sizeConst)
        for const in self.constList:
            if const == 'BoolTrue' or const == 'BoolFalse':
                buffer += self.lub.getUInt8(1)
                buffer += self.lub.getUInt8(1 if const == 'BoolTrue' else 0)
            elif type(const) == float:  ## float64????
                buffer += self.lub.getUInt8(3)
                buffer += self.lub.getDouble(const)
            elif type(const) == str:
                buffer += self.lub.getUInt8(4)
                string = self.lub.getStringUTF8(const)
                buffer += self.lub.getUInt64(len(string))
                buffer += string
            elif const is None:
                buffer += self.lub.getUInt8(0)
            else:
                sys.exit(f'not setup for {const}')
                
        # Proto
        buffer += self.lub.getUInt32(self.sizeProto)
        for i, proto in enumerate(self.protoList):
            proto.build(vanilla, buffer)

        # Positions
        buffer += self.lub.getUInt32(0)

        # Locals
        buffer += self.lub.getUInt32(0)

        # upvalues
        buffer += self.lub.getUInt32(0)

        return buffer


    def print(self, indent=0):
        print(' '*indent, 'Max stack size:', self.maxStackSize)
        print(' '*indent, 'Num Param:', self.numParam)
        print(' '*indent, 'Num UpVal:', self.numUpVal)

        def getNum(x):
            e = x >> 3
            if e > 0:
                m = (x & 0b0111) + 0b1000
                return m * 2 ** (e - 1)
            return x
        
        regDict = {}
        print(self.localList)
        tableReg = []
        tableNum = []
        localScope = {}
        localReg = self.numParam
        localIdx = self.numParam

        for i, instr in enumerate(self.instrList):
            # Reset local register if needed
            if i in localScope:
                print(i, 'reset local reg', localReg, '->', localScope[i])
                print('local idx', localIdx)
                localReg = localScope[i]
            
            if instr.C is None:
                C = ''
            else:
                C = instr.C
            if instr.B < len(self.constList) and instr.B >= 0:
                constVal = self.constList[instr.B]
            else:
                constVal = ""
            name = ""
            if instr.name == 'GETGLOBAL':
                regDict[instr.A] = self.constList[instr.B]
            elif instr.name == 'LOADK':
                regDict[instr.A] = self.constList[instr.B]
            elif instr.name == 'CALL':
                pass
            elif instr.name == 'NEWTABLE':
                if tableReg == [] and tableNum == []:
                    if instr.A > localReg:
                        regDict[instr.A] = 'START TABLE'
                    elif instr.A >= len(self.localList):
                        regDict[instr.A] = 'START TABLE'
                    elif instr.A == localReg:
                        regDict[instr.A] = self.localList[localIdx]
                        localReg += 1
                        localIdx += 1
                    else:
                        sys.exit()
                else:
                    regDict[instr.A] = ''
                tableReg.append(getNum(instr.B))
                tableNum.append(getNum(instr.C))
            elif instr.name == 'SETTABLE':
                if tableNum:
                    tableNum[-1] -= 1
                    if tableNum[-1] == 0 and tableReg[-1] == 0:
                        tableNum.pop()
                        tableReg.pop()
                if instr.B > 0xFF:
                    _B = self.constList[instr.B & 0xFF]
                else:
                    _B = f'Reg[{instr.B}]'
                if instr.C > 0xFF:
                    _C = self.constList[instr.C & 0xFF]
                else:
                    _C = f'Reg[{instr.C}]'
                regDict[instr.A] = f"{_B}: {_C}"
            elif instr.name == 'SETLIST':
                reg = tableReg.pop()
                num = tableNum.pop()
                assert reg > 0, f"reg={reg}"
                assert num == 0, f"num={num}"
                regDict[instr.A] = ''
            elif instr.name == 'SETGLOBAL':
                regDict[instr.A] = f"SET GLOBAL TO {self.constList[instr.B]}"
            elif instr.name == 'SELF':
                if instr.C > 0xFF:
                    regDict[instr.A] = f"{regDict[instr.A]}:{self.constList[instr.C & 0xFF]}"
                else:
                    regDict[instr.A] = f"{regDict[instr.A]}:Reg[{instr.A}]"
            elif instr.name == 'CLOSURE':
                regDict[instr.A] = ''
            elif instr.name == 'RETURN':
                regDict[instr.A] = ''
            elif instr.name == 'JMP':
                localScope[i+instr.B+1] = localReg

            try:
                name = regDict[instr.A]
            except:
                name = ""
                
            print(' '*indent, '[', str(i).rjust(3, ' '), ']', instr.name.rjust(12, ' '), ' : ',
                  str(instr.A).rjust(3, ' '), str(instr.B).rjust(3, ' '), str(C).rjust(3, ' '),
                  str(name).ljust(20, ' '))#, instr.__doc__)
        print('')
        print('')
        print('')
        print(' '*indent, 'Constants')
        for i, const in enumerate(self.constList):
            print(' '*indent, str(i).rjust(2, ' '), ':', const)
        print('')
        print('')
        print('')
        print(' '*indent, 'Local')
        for i, (var, start, end) in enumerate(self.localList):
            print(' '*indent, i, var.ljust(20, ' '), str(start).rjust(5, ' '), str(end).rjust(5, ' '))
        print('')
        print('')
        print('')
        print(' '*indent, 'UpVals')
        for i, var in enumerate(self.upValList):
            print(' '*indent, i, var.ljust(20, ' '))#, str(start).rjust(5, ' '), str(end).rjust(5, ' '))

        for i, chunk in enumerate(self.protoList):
            print('')
            print('')
            print('')
            s = len(str(i)) + 2
            print(' '*indent, '========' + '='*s)
            print(' '*indent, '| Proto', i, '|')
            print(' '*indent, '========' + '='*s)
            print('')
            chunk.print(indent+4)
        

class Table:
    def __init__(self, chunk, instrList):
        self.chunk = chunk
        assert instrList[0].name == 'NEWTABLE'
        self.instrList = self.loadTable(instrList)

    def _getNum(self, x):
        e = x >> 3
        if e > 0:
            m = (x & 0b0111) + 0b1000
            return m * 2 ** (e - 1)
        return x

    def loadTable(self, instrList):
        instr = instrList.pop(0)
        assert instr.name == 'NEWTABLE'
        lst = [instr]
        if instr.B > 0 and instr.C == 0:
            n_tables = 0
            _instr = instrList.pop(0)
            while _instr.name != 'SETLIST' or n_tables > 0:
                lst.append(_instr)
                n_tables += _instr.name == 'NEWTABLE' and _instr.B > 0
                n_tables -= _instr.name == 'SETLIST'
                _instr = instrList.pop(0)
            lst.append(_instr)
        elif instr.B == 0 and instr.C > 0:
            C = self._getNum(instr.C)
            while C > 0:
                if instrList[0].name == 'NEWTABLE':
                    lst += self.loadTable(instrList)
                else:
                    C -= 1
                    lst.append(instrList.pop(0))
        elif instr.B == 0 and instr.C == 0:
            sys.exit(f'Not setup for tables of arbitrary size: {instr}')
        else:
            sys.exit(f'loading table not working for {instr}')
        return lst


    def addEntry(self, key, value):
        assert type(key) == str
        if type(value) == int:
            value = float(int)
        assert type(value) == float
        assert self.instrList[0].name == 'NEWTABLE'
        assert self.instrList[0].B == 0
        self.instrList[0].C += 1
        assert self.instrList[-1].name == 'SETTABLE'
        instr = deepcopy(self.instrList[-1])
        instr.B = 0x100 + self.chunk.getConstIdx(key)
        instr.C = 0x100 + self.chunk.getConstIdx(value)
        self.instrList.append(instr)

    def getInstructions(self):
        instructions = []
        for instr in self.instrList:
            if isinstance(instr, Instruction):
                instructions.append(instr)
            else:
                instructions += instr.getInstructions()
        return instructions

    def addEntry(self, key, value):
        assert type(key) == str
        if type(value) == int:
            value = float(int)
        assert type(value) == float
        assert self.instrList[0].name == 'NEWTABLE'
        assert self.instrList[0].B == 0
        self.instrList[0].C += 1
        assert self.instrList[-1].name == 'SETTABLE'
        instr = deepcopy(self.instrList[-1])
        instr.B = 0x100 + self.chunk.getConstIdx(key)
        instr.C = 0x100 + self.chunk.getConstIdx(value)
        self.instrList.append(instr)

    def _getTable(self, instrList):
        instr = next(instrList)
        assert instr.name == 'NEWTABLE'
        n_tables = instr.B
        n_values = instr.C

        if instr.C > 0:
            table = {}
            C = instr.C
            while instrList.peek(None) and C:
                C -= 1
                if instrList.peek().name == 'NEWTABLE':
                    t = self._getTable(instrList)
                    instr = next(instrList)
                    k = self.chunk.getConst(instr.B & 0xFF)
                    assert len(t) == 1
                    table[k] = t[0]
                elif instrList.peek().name == 'SETTABLE':
                    instr = next(instrList)
                    k = self.chunk.getConst(instr.B & 0xFF)
                    v = self.chunk.getConst(instr.C & 0xFF)
                    table[k] = v
                else:
                    sys.exit()
            return [table]

        elif instr.B > 0:
            tables = []
            while instrList.peek(None) and instrList.peek().name == 'NEWTABLE':
                tables += self._getTable(instrList)
            return tables

    def getTable(self):
        instrList = peekable(self.instrList)
        return self._getTable(instrList)

    def _setTable(self, instrList, values):
        instr = next(instrList)
        if instr.name == 'SETLIST':
            return

        assert instr.name == 'NEWTABLE'

        if instr.C > 0:
            assert isinstance(values, dict)
            for k in values:
                nextInstr = instrList.peek()
                if nextInstr.name == 'NEWTABLE':
                    self._setTable(instrList, values[k])
                    if nextInstr.A > instr.A and instrList.peek().name == 'SETTABLE':
                        next(instrList)
                elif nextInstr.name == 'SETTABLE':
                    instr = next(instrList)
                    idx = self.chunk.getConstIdx(values[k])
                    instr.C = idx + 0x100
                else:
                    sys.exit()

        elif instr.B > 0:
            assert isinstance(values, list)
            for value in values:
                assert instrList.peek().name == 'NEWTABLE'
                self._setTable(instrList, value)

    def setTable(self, values):
        instrList = peekable(self.instrList)
        self._setTable(instrList, values)


# ONLY DEVELOPED FOR THE SIMPLEST FUNCTIONS!
class Function:
    def __init__(self, chunk, instrList):
        self.chunk = chunk
        self.instrList = instrList
        self.newLines = []
        self.isDeleted = False
        self.argDict = {}
        self.tableDict = {}
        self.funcDict = {}
        reg = instrList[0].A
        for instr in instrList:
            if isinstance(instr, Instruction):
                self.argDict[instr.A-reg] = instr
            elif isinstance(instr, list) and instr[0].name == 'NEWTABLE':
                A = instr[0].A
                self.tableDict[A-reg] = instr
            elif isinstance(instr, Table):
                # Temporary, not really needed
                A = instr.getInstructions()[0].A
                self.tableDict[A-reg] = instr
            elif isinstance(instr, Function):
                A = instr.getInstructions()[0].A
                self.funcDict[A-reg] = instr

    def getInstructions(self):
        instr = []
        if not self.isDeleted:
            instr += list(self.instrList)
        for newLine in self.newLines:
            instr += newLine.getInstructions()
        return instr

    def copyLine(self):
        newLine = Function(self.chunk, deepcopy(self.instrList))
        self.newLines.append(newLine)
        return newLine

    def deleteLine(self):
        self.isDeleted = True

    def getArg(self, idx):
        assert idx > 0, "Argument indexing starts at 1"
        if idx in self.argDict:
            instr = self.argDict[idx]
            if instr.name == 'MOVE':
                return self.chunk.getLocal(instr.B)
            elif instr.name == 'GETGLOBAL':
                return self.chunk.getConst(instr.B)
            elif instr.name == 'LOADK':
                return self.chunk.getConst(instr.B)
            else:
                sys.exit(f'setArg not setup for opcode {instr.name}')
        elif idx in self.tableDict:
            return Table(self.chunk, list(self.tableDict[idx]))

    def setArg(self, idx, value):
        assert idx > 0, "Argument indexing starts at 1"
        if idx in self.argDict:
            instr = self.argDict[idx]
            if instr.name == 'MOVE':
                instr.B = self.chunk.getLocalIdx(value)
            elif instr.name == 'GETGLOBAL':
                instr.B = self.chunk.getConstIdx(value)
            elif instr.name == 'LOADK':
                instr.B = self.chunk.getConstIdx(value)
            else:
                sys.exit(f'setArg not setup for opcode {instr.name}')
        elif idx in self.tableDict:
            sys.exit(f'Set table outside of this method')


class Lub:
    def __init__(self, pak, filename=None):
        self.pak = pak
        self.filename = filename
        data = pak.extractFile(filename)
        self.loadLub(data)

    def loadLub(self, data, patch=True):
        self.lub = File(data)            
        
        # Patch data as needed
        if patch:
            basename, _ = os.path.splitext(os.path.basename(self.filename))
            patchFile = get_filename(f'patch/{basename}.patch')
            if os.path.isfile(patchFile):
                with open(patchFile, 'rb') as file:
                    patch = bytes(file.read())
                self.lub.patchData(patch)

        self.vanilla = bytearray(self.lub.data.getbuffer())
        self.loadHeader()
        self.loadFunction()
        self.chunkList = self.listAllChunks(self.topLevel)
        for i, chunk in enumerate(self.chunkList):
            try:
                chunk.organize() # Organize function and table instructions for later access
            except:
                chunk.organize() # Organize function and table instructions for later access

    def loadHeader(self):
        self.lub.data.seek(0)
        assert self.lub.readUInt32() == 0x61754c1b

        self.version = self.lub.readUInt8()
        assert self.version == 0x51

        self.formatVersion = self.lub.readUInt8()
        assert self.formatVersion == 0

        self.endianness = 'big' if self.lub.readUInt8() == 0 else 'little'
        assert self.endianness == 'little'

        self.sizeOfInt = self.lub.readUInt8()
        assert self.sizeOfInt == 4

        self.size_t = self.lub.readUInt8()  ## Size of string, default 4
        assert self.size_t == 8, f'String size is {self.size_t} bytes, not 8 bytes!'

        self.sizeOfInstr = self.lub.readUInt8()
        assert self.sizeOfInstr == 4

        self.sizeLuaNum = self.lub.readUInt8()
        assert self.sizeLuaNum == 8

        self.integralFlag = 'floating' if self.lub.readUInt8() == 0 else 'integral'
        assert self.integralFlag == 'floating'

    def buildHeader(self):
        header = bytearray()
        header += self.lub.getUInt32(0x61754c1b)
        header += self.lub.getUInt8(self.version)
        header += self.lub.getUInt8(self.formatVersion)
        header += self.lub.getUInt8(0 if self.endianness == 'big' else 1)
        header += self.lub.getUInt8(self.sizeOfInt)
        header += self.lub.getUInt8(self.size_t)
        header += self.lub.getUInt8(self.sizeOfInstr)
        header += self.lub.getUInt8(self.sizeLuaNum)
        header += self.lub.getUInt8(0 if self.integralFlag == 'floating' else 1)
        return header


    def loadFunction(self):
        self.topLevel = Chunk(self.lub)
        assert self.lub.tell() == self.lub.data.getbuffer().nbytes, 'Not at the end of the file!!!'

    def listAllChunks(self, chunk):
        lst = [chunk]
        for proto in chunk.protoList:
            lst += self.listAllChunks(proto)
        return lst

    def diff_idx(self, a, b):
        for i, (ai, bi) in enumerate(zip(a, b)):
            if ai != bi:
                return i
        return -1

    def getLocalTable(self, varname):
        tables = []
        for chunk in self.chunkList:
            if varname in chunk.instrTables:
                tables.append(chunk.instrTables[varname])
        if len(tables) == 0:
            return
        if len(tables) == 1:
            if len(tables[0]) == 1:
                return tables[0][0]
            return tables[0]
        return tables

    def getLocalFunction(self, varname):
        functions = []
        for chunk in self.chunkList:
            if varname in chunk.instrFunctions:
                functions.append(chunk.instrFunctions[varname])
        if len(functions) == 0:
            return
        if len(functions) == 1:
            return functions[0]
        return functions

    # Filter instructions by arguments associated with the command
    def getCommandInstr(self, command):

        def getInstr(chunk):
            argInstr = []
            instrList = iter(chunk.instrList[::-1])
            for instr1 in instrList:
                if instr1.name == 'CALL':
                    reg = instr1.A
                    lst = []
                    while True:
                        instr2 = next(instrList)
                        if instr2.A == reg:
                            break
                        lst.append(instr2)
                    if chunk.getConst(instr2.B) == command:
                        argInstr.append(lst[::-1])
            return argInstr

        argInstr = {}
        argInstr[self.topLevel] = getInstr(self.topLevel)
        for proto in self.topLevel.protoList:
            argInstr[proto] = getInstr(proto)

        # Filter empty lists of instructions
        return {c:l for c,l in argInstr.items() if l}

    def hasConst(self, value):
        return self.topLevel.hasConst(value)

    def getConstIdx(self, value):
        return self.topLevel.getConstIdx(value)

    def getConst(self, index):
        return self.topLevel.getConst(index)

    def addConst(self, value):
        self.topLevel.addConst(value)

    def modValue(self):
        self.addConst(2)
        idx = len(self.topLevel.constList) - 1
        self.topLevel.instrList[30].B = idx
        self.addConst(22)
        idx = len(self.topLevel.constList) - 1
        self.topLevel.instrList[29].B = idx

    def update(self):
        header = self.buildHeader()
        chunk = self.topLevel.build(self.vanilla[len(header):])
        newlub = header + chunk
        idx = self.diff_idx(newlub, self.vanilla)
        self.pak.updateData(self.filename, newlub)
        # assert newlub == self.vanilla, f"{self.filename} is not reproduced. First error at idx {idx}"

    def printInstr(self, filename):
        filename = filename.split('.')[0] + '.txt'
        with open(f"out/{filename}", 'w') as sys.stdout:
            self.topLevel.print()
        sys.stdout = sys.__stdout__

    def print(self):
        self.topLevel.print()


class TestLub(Lub):
    def __init__(self, filename):
        self.filename = filename
        with open(filename, 'rb') as f:
            self.lub = File(f.read())
        self.vanilla = bytearray(self.lub.data.getbuffer())
        self.loadHeader()
        self.loadFunction()
        self.chunkList = self.listAllChunks(self.topLevel)

    def update(self):
        header = self.buildHeader()
        chunk = self.topLevel.build(self.vanilla[len(header):])
        return header + chunk

    def dumpNew(self):
        newlub = self.update()
        output = self.filename.replace('.lub', '_new.lub')
        with open(output,'wb') as file:
            file.write(newlub)


def main():
    filename = sys.argv[1]
    lub = TestLub(filename)
    lub.print()


# if __name__=='__main__':
#     main()
