import random
from Lub import Lub
from Assets import Data
from Utility import Byte, File
from copy import deepcopy
from math import sqrt
from itertools import combinations
# import matplotlib.pyplot as plt


# Various unknowns here
# Only get the important stuff 
class Tile(Byte):
    def __init__(self, f, idx, tot):
        # Make sure the tile starts where it should
        assert f.readUInt32() > 0xFFFF0000
        f.data.seek(-4, 1)

        # Parse the tile data
        self.start = f.tell()
        self.height = f.readUInt8()
        self.downLadder = f.readUInt8()
        assert self.height >= self.downLadder
        assert f.readUInt32() == 0xFFFF
        self.unknown1 = f.readBytes(6)
        self.tiletype = f.readString()
        self.unknown2 = f.readBytes(0x30)
        self.num_specs = f.readUInt32()
        self.specs = [f.readString() for _ in range(self.num_specs)]
        if idx+1 != tot:
            s = f.tell()
            while f.readUInt32() < 0xFFFF0000:
                f.data.seek(-3, 1)
            f.data.seek(-4, 1)
            self.end = f.tell()
            f.data.seek(s)
            self.unknown3 = f.readBytes(self.end - s)
        else:
            self.unknown3 = bytearray()
            self.end = f.tell() # Presumably the last unknown will never need to be changed!

        # Store vanilla for initial building
        f.data.seek(self.start)
        self.vanilla = f.readBytes(self.end - self.start)
        self.isModded = False

    def getTileType(self):
        return self.tiletype.split('_')[-1].lower()

    def removeSpec(self, spec):
        assert spec in self.specs
        self.specs.remove(spec)
        self.num_specs -= 1
        assert self.num_specs == len(self.specs)
        self.isModded = True

    def addSpec(self, spec):
        assert spec not in self.specs
        self.specs.append(spec)
        self.num_specs += 1
        assert self.num_specs == len(self.specs)
        self.isModded = True

    def build(self):
        d = self.getUInt8(self.height)
        d += self.getUInt8(self.downLadder)
        d += self.getUInt32(0xFFFF)
        d += self.unknown1
        d += self.getString(self.tiletype)
        d += self.unknown2
        assert self.num_specs == len(self.specs)
        d += self.getUInt32(self.num_specs)
        for spec in self.specs:
            d += self.getString(spec)
        d += self.unknown3
        if not self.isModded:
            assert d == self.vanilla
        return d


class MAP:
    def __init__(self, pak, filename, allow=None):
        self.pak = pak
        self.filename = filename
        self.data = Data(pak, self.filename)
        self.uasset = self.data.uasset
        self.mapData = self.getMapData()
        self.allow = allow
        
        self.chunks = []
        self.maps = []

        self.mapData.data.seek(0)
        i = 0
        while self.loadMap():
            print('  Loaded', self.filename, 'index', i)
            m = self.maps[-1]
            i += 1

    def getMapData(self):
        assert len(self.uasset.exports) == 1
        return File(self.uasset.exports[1].uexp1['bulkData'].array)

    def setMapData(self):
        self.buildMap()
        self.uasset.exports[1].uexp1['bulkData'].array = self.mapData.getData()

    def loadMap(self):
        start = self.mapData.tell()
        while self.mapData.tell() < self.mapData.size - 4:
            if self.mapData.readUInt32() > 0xFFFF0000:
                self.mapData.data.seek(-4, 1)
                self.mapData.data.seek(-10, 1)
                end = self.mapData.tell()
                self.mapData.data.seek(start)
                self.chunks.append(self.mapData.readBytes(end-start))  ## Header/filler data
                m = TileMap(self.mapData, self.allow)  ## Tile map
                self.maps.append(m)
                return True
            else:
                self.mapData.data.seek(-3, 1)
        end = self.mapData.tell()
        self.mapData.data.seek(start)
        self.chunks.append(self.mapData.readBytes())  ## Footer
        assert len(self.chunks) == len(self.maps) + 1
        return False

    def buildMap(self):
        # Build and update UExp
        assert len(self.chunks) == len(self.maps)+1
        chunks = list(self.chunks)
        newMapData = bytearray()
        for m in self.maps:
            newMapData += chunks.pop(0)  # Header + data in between maps
            newMapData += m.build()      # Bunch of tiles from map
        newMapData += chunks.pop(0)      # Footer
        self.mapData.setData(newMapData)

    def update(self, force=False):
        self.setMapData()
        self.data.update(force)


# Cannot parse the uexp file completely, hence the use of File
# and UAsset
class TileMap:
    def __init__(self, f, allow=None):
        self.f = f
        self.include = set()
        self.omit = set(['water', 'obstacle','nopass','none', # 'roof',
                         'nopass_hit_by_knockback', 'none_nopass',
                         'magma', 'great_magma', 'thorn'])

        if allow is not None:
            self.omit = self.omit.difference(allow)

        self.tiles = None
        self.height1 = None
        self.height2 = None
        self.nx = None
        self.ny = None
        self.tileDict = None
        self.specDict = None
        self.changeHeightDict = None
        self.header = None
        self.footer = None
        # self.isLoaded = False

        self.load()
        self.fillChangeHeight()

        valid_x, valid_y = zip(*self.getValid())
        self.centerPoint = (sum(valid_x)//len(valid_x), sum(valid_y)//len(valid_y))
        self.range_x = max(valid_x) - min(valid_x)
        self.range_y = max(valid_y) - min(valid_y)
        
    # original -> target
    def swapSpecs(self, io, jo, it, jt):
        specs = list(self.tileDict[(io,jo)].specs)
        for spec in specs:
            self.tileDict[(io,jo)].removeSpec(spec)
            self.tileDict[(it,jt)].addSpec(spec)

    def moveSpec(self, spec, io, jo, it, jt):
        # assert self.isLoaded, 'Map grid not loaded!'
        assert spec in self.tileDict[(io,jo)].specs
        self.tileDict[(io,jo)].removeSpec(spec)
        self.tileDict[(it,jt)].addSpec(spec)

    def setSpec(self, spec, i, j):
        # assert self.isLoaded, 'Map grid not loaded!'
        assert spec not in self.tileDict[(i,j)].specs
        self.tileDict[(i,j)].addSpec(spec)
        self.specDict[spec].add((i,j))

    def removeSpec(self, spec, i, j):
        # assert self.isLoaded, 'Map grid not loaded!'
        assert spec in self.tileDict[(i,j)].specs
        self.tileDict[(i,j)].removeSpec(spec)

    def clearSpecs(self, spec):
        if spec not in self.specDict:
            return
        for idx in self.specDict[spec]:
            self.tileDict[idx].removeSpec(spec)
            assert self.tileDict[idx].num_specs == len(self.tileDict[idx].specs)
        self.specDict[spec] = set()

    def addSpec(self, spec, idxs):
        if spec not in self.specDict:
            self.specDict[spec] = set()
        for idx in idxs:
            self.tileDict[idx].addSpec(spec)
            self.specDict[spec].add(idx)
            assert self.tileDict[idx].num_specs == len(self.tileDict[idx].specs)

    def getSpec(self, i, j):
        return self.tileDict[(i,j)].specs

    def getIdxs(self, specs):
        idxs = set()
        if specs == set() or specs is None:
            for k, v in self.tileDict.items():
                if not v.specs and self.isValid(*k):
                    idxs.add(k)
            return sorted(idxs)
        if type(specs) == str:
            specs = [specs]
        for s in specs:
            idxs.update(self.specDict[s])
        return sorted(idxs)

    def load(self):
        self.offset = self.f.tell()
        self.nx = self.f.readUInt16()
        self.ny = self.f.readUInt16()
        assert self.f.readUInt16() == self.nx
        tot = self.f.readUInt32()
        assert tot == self.nx * self.ny

        self.tileDict = {}
        for idx in range(tot):
            i = idx % self.nx
            j = idx // self.nx
            self.tileDict[(i,j)] = Tile(self.f, idx, tot)
        
        # Store all the data for dumping
        self.tiles = []
        self.height1 = []
        self.height2 = []
        self.specDict = {}
        tileTypes = set()
        for j in range(self.ny):
            t = []
            h1 = []
            h2 = []
            i = 0
            for i in range(self.nx):
                t.append(self.tileDict[(i,j)].getTileType())
                h1.append(self.tileDict[(i,j)].height)
                h2.append(self.tileDict[(i,j)].downLadder)
                for spec in self.tileDict[(i,j)].specs:
                    if spec not in self.specDict:
                        self.specDict[spec] = set()
                    self.specDict[spec].add((i,j))
            self.tiles.append(t)
            self.height1.append(h1)
            self.height2.append(h2)
            tileTypes.update(t)

        # Update tile stuff
        self.include = tileTypes.difference(self.omit)
        self.omit = tileTypes.intersection(self.omit)

        # Store as grid
        self.grid = deepcopy(self.height1)
        for g, t in zip(self.grid, self.tiles):
            for i, (gi, ti) in enumerate(zip(g, t)):
                if ti in self.omit:
                    g[i] = -1

    def fillChangeHeight(self):
        self.changeHeightDict = {}
        for p, _ in self.tileDict.items():
            h = self.getHeight(*p)
            dh = 0

            nh = self.getHeight(p[0]+1, p[1])
            if nh is not None:
                dh = max(dh, h - nh)

            nh = self.getHeight(p[0]-1, p[1])
            if nh is not None:
                dh = max(dh, h - nh)

            nh = self.getHeight(p[0], p[1]+1)
            if nh is not None:
                dh = max(dh, h - nh)

            nh = self.getHeight(p[0], p[1]-1)
            if nh is not None:
                dh = max(dh, h - nh)

            if dh not in self.changeHeightDict:
                self.changeHeightDict[dh] = []

            self.changeHeightDict[dh].append(p)

    def printSpecs(self):
        # assert self.isLoaded, 'Map grid not loaded!'
        for (x,y), t in self.tileDict.items():
            if t.specs:
                print(x, y, t.specs)

    def build(self):
        m = bytearray()
        m += self.f.getUInt16(self.nx)
        m += self.f.getUInt16(self.ny)
        m += self.f.getUInt16(self.nx)
        m += self.f.getUInt32(self.nx*self.ny)
        for tile in self.tileDict.values():
            m += tile.build()
        return m

    def isValid(self, i, j):
        if i < 0 or i >= self.nx or j < 0 or j >= self.ny:
            return False
        return self.grid[j][i] > 0

    def getValid(self):
        valid = []
        for j in range(self.ny):
            for i in range(self.nx):
                if self.isValid(i, j):
                    valid.append((i,j))
        return valid

    def getInvalid(self):
        invalid = []
        for j in range(self.ny):
            for i in range(self.nx):
                if not self.isValid(i, j):
                    invalid.append((i,j))
        return invalid

    def setInvalid(self, i, j):
        self.grid[j][i] = -1

    def isHeight(self, i, j, h, tol=0):
        dh = self.getHeight(i, j) - h
        return abs(dh) <= tol

    def getHeight(self, i, j, validCheck=True):
        if validCheck and not self.isValid(i, j):
            return 1e9
        if i < 0 or i >= self.nx or j < 0 or j >= self.ny:
            return 1e9
        return self.height1[j][i]
        # if self.isValid(i, j):
        #     return self.grid[j][i]
        # return None

    def heightDiffTiles(self, dh=2):
        def checkTile(h, i, j):
            d = h - self.getHeight(i, j)
            return d > dh and d < 100

        tiles = []
        for i in range(self.nx):
            for j in range(self.ny):
                h = self.getHeight(i, j)
                if checkTile(h, i+1, j):
                    tiles.append((i+1, j))
                    continue
                elif checkTile(h, i-1, j):
                    tiles.append((i-1, j))
                    continue
                elif checkTile(h, i, j+1):
                    tiles.append((i, j+1))
                    continue
                elif checkTile(h, i, j-1):
                    tiles.append((i, j-1))
                    continue

        return tiles

    def isType(self, i, j, t):
        return self.getType(i,j) == t

    def getType(self, i, j):
        if self.isValid(i,j):
            return self.tileDict[(i,j)].getTileType()
        return None

    def filterTileTypes(self, t):
        t = t.lower()
        tileList = []
        for key, tile in self.tileDict.items():
            if tile.getTileType() == t:
                tileList.append(key)
        return tileList            

    # def plot(self, filename):
    #     if self.tiles is None:
    #         return

    #     def p(g, s=None):
    #         if s and self.specDict[s] == set():
    #             return
    #         fig, ax = plt.subplots()
    #         fig.set_size_inches(11, 8)
    #         ax.invert_yaxis()
    #         x = list(range(self.nx+1))
    #         y = list(range(self.ny+1))
    #         ax.pcolor(x, y, g, edgecolors='k', linewidths=2)
    #         dx = 1 if self.nx < 40 else 2
    #         dy = 1 if self.ny < 40 else 2
    #         ax.set_xticks([0.5+i for i in range(0, self.nx, dx)])
    #         ax.set_xticklabels([i for i in range(0, self.nx, dx)])
    #         ax.set_yticks([0.5+i for i in range(0, self.ny, dy)])
    #         ax.set_yticklabels([i for i in range(0, self.ny, dy)])
    #         if s and s in self.specDict:
    #             m_x, m_y = list(zip(*self.specDict[s]))
    #             m_x = [m+0.5 for m in m_x]
    #             m_y = [m+0.5 for m in m_y]
    #             ax.scatter(m_x, m_y, marker='X', s=100, color="black")
    #             plt.title(f"{filename.split('/')[-1].split('.')[0]}\nOmit: " + ', '.join(self.omit) + f'\n{s}')
    #             plt.show()
    #         else:
    #             plt.title(f"{filename.split('/')[-1].split('.')[0]}\nOmit: " + ', '.join(self.omit))
    #             plt.show()
    #         plt.close()

        p(self.grid)
        for s in self.specDict:
            p(self.grid, s=s)
        # p(self.grid, n=f"{base}_grid.pdf")
        # p(self.height1, n=f"{base}_height1.pdf")
        # p(self.height2, n=f"{base}_height2.pdf")

    def _makeLine(self, candidates, pt=None):
        if pt is None:
            x, y = random.sample(sorted(candidates), 1)[0]
        else:
            x, y = pt
        h = self.getHeight(x, y)
        t = self.getType(x, y)

        def traverse(dx, dy):
            xi = x
            yi = y
            line = [(xi, yi)]
            while True:
                xi += dx
                yi += dy
                if (xi, yi) not in candidates:
                    break
                if not self.isValid(xi, yi):
                    break
                if not self.getHeight(xi, yi) == h:
                    break
                if not self.getType(xi, yi) == t:
                    break
                line.append((xi, yi))
            return line

        horiz  = traverse( 1,  0)
        horiz += traverse(-1,  0)
        vert   = traverse( 0,  1)
        vert  += traverse( 0, -1)

        horiz = set(horiz)
        vert = set(vert)
        return horiz, vert

    # Returns the shortest line at fixed height and spec
    def flatLine(self, candidates, length=None, pt=None):
        horiz, vert = self._makeLine(candidates, pt)

        if length:
            if len(horiz) < length and len(vert) < length:
                return set()
            elif len(horiz) >= length and len(vert) >= length:
                if random.random() < 0.5:
                    t = horiz
                else:
                    t = vert
            elif len(horiz) >= length:
                t = horiz
            else:
                t = vert
            i = random.randint(0, len(t)-length)
            t = sorted(t)
            return set(t[i:i+length])

        if len(horiz) < len(vert):
            return horiz
        elif len(vert) > len(horiz):
            return vert
        else:
            if random.random() < 0.5:
                return horiz
            else:
                return vert

    def flatLineLong(self, candidates, pt=None):
        horiz, vert = self._makeLine(candidates, pt)
        if len(horiz) > len(vert) + random.random() - 0.5:
            return horiz
        else:
            return vert

    def randomNearbyPoint(self, point, d, candidates, dh=2, n=1, tol=3):
        def calcDist2(p):
            x = p[0] - point[0]
            y = p[1] - point[1]
            return abs(x*x + y*y - d*d)

        h = self.getHeight(*point)
        candidates = sorted(candidates)
        grid = []
        for p in candidates:
            if p == point: continue
            if calcDist2(p) < tol*tol:
                ph = self.getHeight(*p)
                if abs(ph - h) <= dh:
                    grid.append(p)

        if len(grid) == 0:
            return None

        grid = sorted(grid)
        if n == 1:
            return random.sample(grid, 1)[0]
        elif n > len(grid):
            return grid
        else:
            return random.sample(grid, n)

    def surroundSpec(self, spec, specNew, n=3):
        idxs = self.specDict[spec]
        idx_x, idx_y = list(zip(*idxs))
        min_x = min(idx_x) - n
        max_x = max(idx_x) + n
        min_y = min(idx_y) - n
        max_y = max(idx_y) + n
        idxs = set()
        for i in range(min_x, max_x+1):
            for j in range(min_y, max_y+1):
                idx = (i,j)
                if not self.isValid(i,j):
                    continue
                if spec in self.tileDict[idx].specs:
                    continue
                self.setSpec(specNew, i, j)
                idxs.add((i,j))
        self.specDict[specNew] = idxs

    def lineXSpec(self, spec, yi, yf, omit=None):
        if omit is None:
            omit = set()
        assert yi < yf
        for j in range(yi, yf+1):
            for i in range(self.nx):
                if self.isValid(i, j):
                    if omit.isdisjoint(self.getSpec(i, j)):
                        self.setSpec(spec, i, j)

    def lineYSpec(self, spec, xi, xf, omit=None):
        if omit is None:
            omit = []
        assert xi < xf
        for i in range(xi, xf+1):
            for j in range(self.ny):
                if self.isValid(i, j):
                    if omit.isdisjoint(self.getSpec(i, j)):
                        self.setSpec(spec, i, j)

    def specUnion(self, specs):
        union = set()
        for spec in specs:
            union.update(self.specDict[spec])
        return union

    def cluster(self, size, specs=None, omit=None, d=2, candidates=None):
        if omit is None:
            omit = set()
        if specs is None:
            specs = set()
        if candidates is None:
            candidates = self.getIdxs(specs)
        else:
            candidates = sorted(candidates)
        x, y = random.sample(candidates, 1)[0]
        while omit.intersection(self.getSpec(x, y)):
            x, y = random.sample(candidates, 1)[0]
        idxs = set()
        while len(idxs) < size:
            idxs.add((x,y))
            x1 = random.randint(x-d, x+d)
            y1 = random.randint(y-d, y+d)
            if self.isValid(x1, y1):
                s = self.getSpec(x1, y1)
                if (specs.intersection(s) and omit.isdisjoint(s)) or \
                   (not specs and not s):
                    x = x1
                    y = y1
        return sorted(idxs)

    def nearbyCluster(self, point, dist, count, candidates, dh=2, tol=3):
        # Pick a point some distance away from the given point
        n_pt = self.randomNearbyPoint(point, dist, candidates, dh=dh, tol=tol)
        if n_pt is None:
            return None
        # Do BFS to get some neighboring points
        cluster = self.bfs(n_pt, count, candidates)
        # Filter invalid points
        grid = []
        for c in cluster:
            if self.isValid(*c):
                if self.shortestPath(c, point):
                    grid.append(c)
        return sorted(grid) # Keep sorted in case any sampling from the cluster is necessary

    def randomCluster(self, count, candidates):
        pt = random.sample(sorted(candidates), 1)[0]
        return self.bfs(pt, count, candidates)

    def randomRectangle(self, start, count, candidates, d=2):
        for _ in range(10):
            # grid = self.bfs(start, count, candidates, d)
            grid = self.randomWalk(start, count, d)
            xmin = self.nx
            xmax = 0
            ymin = self.ny
            ymax = 0
            for x, y in grid:
                xmin = min(x, xmin)
                xmax = max(x, xmax)
                ymin = min(y, ymin)
                ymax = max(y, ymax)

            # Fill as much of the rectangle as possible
            rect = self.bfs(start, 1000, candidates, d, xmin, xmax, ymin, ymax)

            # Shrink the rectangle if it's too huge!
            i = 0
            while len(rect) > 1.3*count:
                n = random.randint(0, 3)
                if n == 0 and xmin < xmax:
                    xmin += 1
                    rect = list(filter(lambda x: x[0] >= xmin, rect))
                elif n == 1 and xmin < xmax:
                    xmax -= 1
                    rect = list(filter(lambda x: x[0] <= xmax, rect))
                elif n == 2 and ymin < ymax:
                    ymin += 1
                    rect = list(filter(lambda y: y[1] >= ymin, rect))
                elif n == 3 and ymin < ymax:
                    ymax -= 1
                    rect = list(filter(lambda y: y[1] <= ymax, rect))
                i += 1
                if i == 10:
                    break

            # Repeat if too large or too small; otherwise done
            if len(rect) <= 1.3*count and len(rect) >= 2:
                return rect

        return rect

    def bfs(self, start, count, candidates, d=2, xmin=None, xmax=None, ymin=None, ymax=None):
        grid = set()
        tried = {c:False for c in candidates}
        tried[start] = False
        queue = [start]
        if xmin is None: xmin = 0
        if xmax is None: xmax = self.nx-1
        if ymin is None: ymin = 0
        if ymax is None: ymax = self.ny-1
        
        while queue and len(grid) < count:
            g = queue.pop(0)

            # Don't repeat
            if g not in tried:
                continue
                # tried[g] = True
            elif tried[g]:
                continue
            tried[g] = True

            # Add to grid
            if g in candidates:
                grid.add(g)

            X, Y = g
            h = self.getHeight(*g)

            if X+1 <= xmax:
                p = (X+1, Y)
                dh = self.getHeight(*p) - h
                if self.isValid(*p) and abs(dh) <= d:
                    queue.append(p)
                elif X+2 <= xmax:
                    p = (X+2, Y)
                    dh = self.getHeight(*p) - h
                    if self.isValid(*p) and abs(dh) <= 1:
                        queue.append(p)

            if X-1 >= xmin:
                p = (X-1, Y)
                dh = self.getHeight(*p) - h
                if self.isValid(*p) and abs(dh) <= d:
                    queue.append(p)
                elif X-2 >= xmin:
                    p = (X-2, Y)
                    dh = self.getHeight(*p) - h
                    if self.isValid(*p) and abs(dh) <= 1:
                        queue.append(p)

            if Y+1 <= ymax:
                p = (X, Y+1)
                dh = self.getHeight(*p) - h
                if self.isValid(*p) and abs(dh) <= d:
                    queue.append(p)
                elif Y+2 <= ymax:
                    p = (X, Y+2)
                    dh = self.getHeight(*p) - h
                    if self.isValid(*p) and abs(dh) <= 1:
                        queue.append(p)

            if Y-1 >= ymin:
                p = (X, Y-1)
                dh = self.getHeight(*p) - h
                if self.isValid(*p) and abs(dh) <= d:
                    queue.append(p)
                elif Y-2 >= ymin:
                    p = (X, Y-2)
                    dh = self.getHeight(*p) - h
                    if self.isValid(*p) and abs(dh) <= 1:
                        queue.append(p)
            
        return sorted(grid)

    def randomHighPoint(self, dh_min=5, candidates=None):
        if candidates is None:
            candidates = set(self.getValid())
        else:
            candidates = set(candidates)
        points = []
        for dh, pts in self.changeHeightDict.items():
            if dh >= dh_min:
                for pt in pts:
                    if self.isValid(*pt) and pt in candidates:
                        points.append((dh, pt))
        return random.sample(points, 1)[0]

    def reachableLowGroundPoint(self, point, target_change=3):
        height = self.getHeight(*point)
        if height < 2:
            return point
        target_height = max(0, height - target_change)
        queue = [(point, height)]
        tried = {p:False for p in self.tileDict}
        while queue:
            p, h = queue.pop(0)
            if h < target_height and self.isValid(*p):
                return p

            if tried[p]:
                continue
            tried[p] = True

            X, Y = p

            g = (X+1, Y)
            hg = self.getHeight(*g)
            dh = abs(h - hg)
            if dh <= 2:
                queue.append((g, hg))
            
            g = (X-1, Y)
            hg = self.getHeight(*g)
            dh = abs(h - hg)
            if dh <= 2:
                queue.append((g, hg))
            
            g = (X, Y+1)
            hg = self.getHeight(*g)
            dh = abs(h - hg)
            if dh <= 2:
                queue.append((g, hg))
            
            g = (X, Y-1)
            hg = self.getHeight(*g)
            dh = abs(h - hg)
            if dh <= 2:
                queue.append((g, hg))
            
            g = (X+2, Y)
            hg = self.getHeight(*g)
            dh = abs(h - hg)
            if dh <= 2:
                queue.append((g, hg))
            
            g = (X-2, Y)
            hg = self.getHeight(*g)
            dh = abs(h - hg)
            if dh <= 2:
                queue.append((g, hg))
            
            g = (X, Y+2)
            hg = self.getHeight(*g)
            dh = abs(h - hg)
            if dh <= 2:
                queue.append((g, hg))
            
            g = (X, Y-2)
            hg = self.getHeight(*g)
            dh = abs(h - hg)
            if dh <= 2:
                queue.append((g, hg))

        return None
            
            
    # A* algorithm
    def shortestPath(self, src, dest, grid=None, block=None):
        if grid is None:
            grid = self.getValid()

        if block is None:
            block = []
        
        def dist(p):
            x = p[0] - dest[0]
            y = p[1] - dest[1]
            return x*x + y*y

        openSet = set([src])
        cameFrom = {}
        gScore = {n: 1e9 for n in grid}
        fScore = {n: 1e9 for n in grid}

        gScore[src] = 0
        fScore[src] = dist(src)

        def reconstructPath(n):
            path = [n]
            while n in cameFrom:
                n = cameFrom[n]
                path.append(n)
            return path

        while openSet:
            # Sort twice to ensure the queue is always in the same order
            # There can be minor differences when running the randomizer
            # from a script, from the gui, from an executable, etc.
            queue = sorted(sorted(openSet), key=lambda n: fScore[n])
            current = queue.pop(0)
            if current == dest:
                return reconstructPath(current)

            openSet.remove(current)
            X, Y = current
            h = self.getHeight(*current)
            for neighbor, neighbor2 in [((X+1, Y), (X+2, Y)),
                                        ((X-1, Y), (X-2, Y)),
                                        ((X, Y+1), (X, Y+2)),
                                        ((X, Y-1), (X, Y-2))]:
                if neighbor in block:
                    continue

                # First pick a neighbor to use
                dh1 = self.getHeight(*neighbor, validCheck=False) - h
                isNeg = dh1 < 0 # Must be negative to allow for jumping over invalid or deep tile
                dh2 = abs(h - self.getHeight(*neighbor2))
                if abs(dh1) <= 2 and neighbor in grid and self.isValid(*neighbor):
                    n = neighbor
                elif isNeg and dh2 <= 1 and neighbor2 in grid and self.isValid(*neighbor2): # Can jump across gap
                    n = neighbor2
                else:
                    continue

                if n not in gScore:
                    continue

                # Omit +2 for neighbor2. it is arguably "shorter" this way
                tmp = gScore[current] + 1
                if tmp < gScore[n]:
                    cameFrom[n] = current
                    gScore[n] = tmp
                    fScore[n] = tmp + dist(n)
                    openSet.add(n)

        return None

        

    # Should this only consider valid points?
    # Omitted since this is mainly used for AI stuff
    #
    # MAYBE ALLOW FOR HEIGHER HEIGHTS TOO?
    def gridSameHeight(self, point, tol=0):
        height = self.getHeight(*point)
        queue = [point]
        tried = {p:False for p in self.tileDict}
        grid = set()
        while queue:
            p = queue.pop(0)
            if tried[p]:
                continue
            tried[p] = True
            
            X, Y = p

            g = (X+1, Y)
            if self.isHeight(*g, height, tol):
            # if self.getHeight(*g) >= height:
                grid.add(g)
                queue.append(g)

            g = (X-1, Y)
            if self.isHeight(*g, height, tol):
            # if self.getHeight(*g) >= height:
                grid.add(g)
                queue.append(g)

            g = (X, Y+1)
            if self.isHeight(*g, height, tol):
            # if self.getHeight(*g) >= height:
                grid.add(g)
                queue.append(g)

            g = (X, Y-1)
            if self.isHeight(*g, height, tol):
            # if self.getHeight(*g) >= height:
                grid.add(g)
                queue.append(g)
                
            g = (X+2, Y)
            if self.isHeight(*g, height, tol):
            # if self.getHeight(*g) >= height:
                grid.add(g)
                queue.append(g)

            g = (X-2, Y)
            if self.isHeight(*g, height, tol):
            # if self.getHeight(*g) >= height:
                grid.add(g)
                queue.append(g)

            g = (X, Y+2)
            if self.isHeight(*g, height, tol):
            # if self.getHeight(*g) >= height:
                grid.add(g)
                queue.append(g)

            g = (X, Y-2)
            if self.isHeight(*g, height, tol):
            # if self.getHeight(*g) >= height:
                grid.add(g)
                queue.append(g)
                
        return sorted(grid)

    def clusterMean(self, cluster):
        x = 0
        y = 0
        for X, Y in cluster:
            x += X
            y += Y
        n = len(cluster)
        return (x//n, y//n)

    def randomEdgePoint(self, grid=None, pt=None):
        # Previously found edge points not accessible to everyone with dh=3.
        # This is a crude fix to that problem.
        def checkPoint(x, y):
            if not self.isValid(x, y):
                return False
            ok = True
            h = self.getHeight(x, y)
            for di, dj in [(1,1), (1,-1), (-1,1), (-1,-1)]:
                x2 = x + di
                y2 = y + dj
                dh = abs(h - self.getHeight(x2, y2))
                ok *= self.isValid(x2, y2)
                ok *= dh <= 2
            return ok
        
        if pt:
            X, Y = pt
        else:
            # Pick a random point on the edge of the map
            if random.random() < 0.5:
                X = random.randint(0, self.nx-1)
                if random.random() < 0.5:
                    Y = 0
                else:
                    Y = self.ny - 1
            else:
                Y = random.randint(0, self.ny-1)
                if random.random() < 0.5:
                    X = 0
                else:
                    X = self.nx - 1

        if checkPoint(X, Y):
            if not grid:
                return X, Y
            elif (X, Y) in grid:
                return X, Y

        # "DFS" to find a valid point
        queue = [(X, Y)]
        visited = {(i,j):False for i,j in self.tileDict.keys()}
        while queue:
            X, Y = queue.pop()
            if (X, Y) not in visited: # OOB
                continue
            if checkPoint(X, Y):
                if not grid:
                    return X, Y
                elif (X, Y) in grid:
                    return X, Y
            if visited[(X, Y)]:
                continue
            visited[(X, Y)] = True
            neighbors = [(X+1, Y), (X-1, Y), (X, Y+1), (X, Y-1)]
            random.shuffle(neighbors)
            queue += neighbors

        return None

    def randomWalk(self, pt, n, d=2):
        points = set()
        if self.isValid(*pt):
            points.add(pt)
        dp = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        w = random.sample(range(1, 10), len(dp))
        i = 0
        s = 0
        while len(points) < n:
            x, y = pt
            dx, dy = random.choices(dp, w, k=1)[0]
            x += dx
            y += dy
            dh = abs(self.getHeight(*pt) - self.getHeight(x, y))
            if self.isValid(x, y) and dh <= d:
                pt = (x, y)
                points.add(pt)

            # Increment only if size of points doesn't grow
            i += s == len(points)
            if i == 100:
                break
            s = len(points)

        return sorted(points)

    def randomWalkGrid(self, n, grid):
        n = min(n, len(grid))
        candidates = sorted(grid)
        pt = random.sample(candidates, 1)[0]
        points = set()
        valid = set(grid)
        dp = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        count = 0
        while len(points) < n:
            x, y = pt
            dx, dy = random.sample(dp, 1)[0]
            x += dx
            y += dy
            if (x, y) in valid:
                pt = (x, y)
                points.add(pt)
            count += 1
            if count%100 == 0:
                pt = random.sample(candidates, 1)[0]
                points = set()
                
        return sorted(points)

    def outlineGrid(self, grid, candidates, length=1):
        outline = set()
        for (X, Y) in grid:
            for i in range(-length, length+1):
                for j in range(-length, length+1):
                    p = (X+i, Y+j)
                    if self.isValid(*p):
                        outline.add(p)
        outline = outline.intersection(candidates).difference(grid)
        return sorted(outline)

    def edgesOfGrid(self, grid=None):
        if grid is None:
            grid = set(self.getValid())
        edges = set(grid)
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for (x, y) in list(edges):
            for dx, dy in dirs:
                pt = (x+dx, y+dy)
                if pt[0] < 0 or pt[0] == self.nx:
                    continue
                if pt[1] < 0 or pt[1] == self.ny:
                    continue
                if not self.isValid(*pt):
                    continue
                if pt not in grid:
                    break
            else:
                edges.remove((x, y))
        return sorted(edges)

    def greatestDistance(self, point, num=None, grid=None, tol=None):
        if tol is None:
            tol = 0

        if grid is None:
            grid = self.getAccessible(*point)
        elif type(grid) == set:
            grid = sorted(grid)

        def calcDist(x, y):
            X = abs(x - point[0])
            Y = abs(y - point[1])
            return max(X, Y)

        furthest = {}
        dmax = 0
        for pt in grid:
            d = calcDist(*pt)
            if d not in furthest:
                furthest[d] = []
            furthest[d].append(pt)
            dmax = max(d, dmax)

        candidates = list(furthest[dmax])
        for _ in range(tol):
            dmax -= 1
            if dmax in furthest:
                candidates += furthest[dmax]

        if num is None:
            return random.sample(candidates, 1)[0]
        else:
            return random.sample(candidates, num)

    def furthestPointsApart(self, grid):
        furthest = {}
        dmax = 0
        for p1, p2 in combinations(grid, 2):
            d = round(self.distance(p1, p2))
            if d not in furthest:
                furthest[d] = []
            furthest[d].append((p1, p2))
            dmax = max(d, dmax)
        return random.sample(furthest[dmax], 1)[0]

    def distance(self, pt1, pt2):
        x1, y1 = pt1
        x2, y2 = pt2
        dx = x1 - x2
        dy = y1 - y2
        return sqrt(dx*dx + dy*dy)

    def dirToCenter(self, pt):
        x, y = pt
        cx, cy = self.centerPoint
        direction = (cx-x, cy-y)
        greatestDir = 'x' if abs(direction[0]/self.range_x) > abs(direction[1]/self.range_y) else 'y'
        if greatestDir == 'x':
            if direction[0] > 0:
                return 'CHAR_DIR_NORTH'
            else:
                return 'CHAR_DIR_SOUTH'
        else:
            if direction[1] > 0:
                return 'CHAR_DIR_EAST'
            else:
                return 'CHAR_DIR_WEST'

    def getAccessible(self, x, y, dh=2, grid=None):
        if grid is None:
            grid = set(self.getValid())
        accessible = self.bfs((x, y), len(grid), grid, d=dh) # dh included as crude fix for ladders on some levels
        return set(self.getValid()).intersection(accessible)
