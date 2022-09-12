import random
# from re import S
from Lub import Lub
import hjson
import os
from Assets import UAsset, Data
from Utility import Byte, File
from copy import deepcopy
from TileMap import MAP
from Positions import POSITION, PLAYERPOSITION, ENEMYPOSITION, SPAWNPOSITION
from math import log10, floor
import sys
import signal

# TODO: Clean up this mess.

class Level:
    def __init__(self, pak, filename, mapIndex, sceneFilename=None):
        self.battle = Lub(pak, f'{filename}.lub')
        self.battleCommon = Lub(pak, f'{filename}_common.lub')
        if sceneFilename == None:
            sceneFilename = f'{filename}_S.lub'
        elif '.lub' not in sceneFilename:
            sceneFilename += '.lub'
        self.battleScene = Lub(pak, sceneFilename)

        mapDirname = '_'.join(filename.split('_')[:2])
        self.mapObj = MAP(pak, f'WBAsset/{mapDirname}/{filename}.uasset')
        self.mapGrid = self.mapObj.maps[mapIndex]

        self.aiObj = Data(pak, f'Story/{mapDirname}/{filename}.umap')

        self.addInitialPositions = self.battle.getLocalFunction('AddInitialPosition')
        self.pcPositions = [PLAYERPOSITION(i, self.mapGrid) for i in self.addInitialPositions]

        enemyPositions = self.battleCommon.getLocalFunction('CreateUnitData')
        self.enemyPositions = [ENEMYPOSITION(i, self.mapGrid) for i in enemyPositions]

        self.initialUnitTable = self.battle.getLocalTable('initailUnitTable')
        assert self.initialUnitTable is not None

        self.initialChargeTimeTable = self.battle.getLocalTable('initialChargeTimeTable')
        assert self.initialChargeTimeTable is not None

        self.isRandomized = False

    def printEnemyPoints(self):
        pts = [(e.X, e.Y) for e in self.enemyPositions]
        return pts

    def printPlayerPoints(self):
        pts = [(e.X, e.Y) for e in self.pcPositions]
        return pts

    # More accurately, all enemies at a position set
    # They could by change be set to their default position 
    def checkAllEnemiesMoved(self):
        allMoved = True
        for i, en in enumerate(self.enemyPositions):
            allMoved *= en.moved
            if not en.moved:
                print("Enemy", i, "is still at point", en.X, ",", en.Y)
        if not allMoved:
            sys.exit(f"{self.__class__.__name__}: Not all enemies moved!")
        return allMoved

    def update(self):
        # Check for errors with PC and enemy locations
        if self.isRandomized:
            pc = set([(p.X, p.Y) for p in self.pcPositions])
            en = set([(e.X, e.Y) for e in self.enemyPositions])
            assert len(pc) == len(self.pcPositions), f"{self.__class__.__name__}: {len(pc)}     {len(self.pcPositions)}"
            assert len(en) == len(self.enemyPositions), f"{self.__class__.__name__}: {len(en)}     {len(self.enemyPositions)}"
            assert pc.isdisjoint(en), list(filter(lambda x: x in en, pc))
            for pc in self.pcPositions:
                for en in self.enemyPositions:
                    dx = abs(en.X - pc.X)
                    dy = abs(en.Y - pc.Y)
                    if dx <= 1 and dy <= 1 and dx+dy <= 2:
                        print(f'Random {self.__class__.__name__}')
                        print((pc.X, pc.Y), (en.X, en.Y))
                        print(sorted([(pc.X, pc.Y) for pc in self.pcPositions]))
                        print(sorted([(en.X, en.Y) for en in self.enemyPositions]))
                        sys.exit('FAILED PC and EN too close!')

        # Update files
        self.battle.update()
        self.battleCommon.update()
        self.battleScene.update()
        self.mapObj.update(force=True) # Temporary, just to help with plotting and testing
        self.aiObj.update(force=True)

    def getAIMoveGrid(self, idx):
        grid = self.aiObj.uasset.exports[idx].uexp1['MovableGrids'].array
        return [(x, y) for x, y, _ in grid]

    def setAIMoveGrid(self, idx, grid):
        array = [(x, y, 0) for x, y in grid]
        self.aiObj.uasset.exports[idx].uexp1['MovableGrids'].array = array

    def getAIAtkGrid(self, idx):
        grid = self.aiObj.uasset.exports[idx].uexp1['AttackableGrids'].array
        return [(x, y) for x, y, _ in grid]

    def setAIAtkGrid(self, idx, grid):
        array = [(x, y, 0) for x, y in grid]
        self.aiObj.uasset.exports[idx].uexp1['AttackableGrids'].array = array

    def updateEnforcedPCs(self, mapPC):
        if self.initialUnitTable is None:
            return
        unitTable = self.initialUnitTable.getTable()
        for i, table in enumerate(unitTable):
            if table['ID'] in mapPC:
                table['ID'] = mapPC[table['ID']]
        self.initialUnitTable.setTable(unitTable)

    def randomTimes(self):
        if self.initialChargeTimeTable is None:
            return None

        timeTable = self.initialChargeTimeTable.getTable()

        # Weighted Fischer-Yates
        def shuffle(weights):
            for i, table in enumerate(timeTable):
                if not weights[i]: continue
                table2 = random.choices(timeTable[i:], weights[i:])[0]
                table['Time'], table2['Time'] = table2['Time'], table['Time']

        # Get weights to shuffle PCs and enemies separately
        w_pc = []
        w_en = []
        for table in timeTable:
            b = "UNIT_MASTER_CH_P" in table['ID']
            w_pc.append(b)
            w_en.append(not b)

        shuffle(w_pc)
        shuffle(w_en)
        self.initialChargeTimeTable.setTable(timeTable)

    def _setBestDirection(self, ref, pos):
        n = self._nearestNeighbor(ref, pos.X, pos.Y)
        pos.bestDirection(n.X, n.Y)

    def setPCDirections(self, allies=None):
        for pc in self.pcPositions:
            self._setBestDirection(self.enemyPositions, pc)
        if allies is None:
            return
        if type(allies) == list:
            for ally in allies:
                self._setBestDirection(self.enemyPositions, ally)
        else:
            self._setBestDirection(self.enemyPositions, allies)

    def setEnemyDirections(self):
        for enemy in self.enemyPositions:
            self._setBestDirection(self.pcPositions, enemy)

    # NB: this does not account for any fixed player position!
    # Examples: ms01_x01 PCs, allies like Exharme, Corentin.
    def setPositions(self, points, units):
        points = sorted(points)
        random.shuffle(points)
        for pt, unit in zip(points, units):
            unit.X, unit.Y = pt

    # TODO: Might need to update contents of the initialTable
    # to make different pcs mandatory (e.g. Roland)
    def setPlayerPositions(self, points, ally=None):
        
        if ally is None:
            ally = []
        elif type(ally) is not list:
            ally = [ally]

        points = sorted(points)
        random.shuffle(points)

        # Setup initial position table -- num of pc positions might change!
        for f in self.addInitialPositions:
            f.deleteLine()
        nPos = len(points) - len(ally)
        self.pcPositions = [PLAYERPOSITION(f.copyLine(), self.mapGrid) for _ in range(nPos)]

        # Assign positions to pcs and allies
        self.setPositions(points, self.pcPositions + ally)

        # Set points in the initial unit table, if necessary
        self.setUnitTable(points)

    def setUnitTable(self, points):
        if type(points) is set:
            points = sorted(points)
            random.shuffle(points)
        tables = self.initialUnitTable.getTable()
        assert len(points) >= len(tables)
        for i, table in enumerate(tables):
            if 'X' in table and 'Y' in table:
                table['X'] = float(points[i][0])
                table['Y'] = float(points[i][1])
        self.initialUnitTable.setTable(tables)

    def setGimmickPositions(self, points, gimmicks, positions, friends=None):
        while gimmicks:
            f = gimmicks.pop()
            f.deleteLine()
        name = positions[0].name
        while not name.isalpha():
            name = name[:-1]
        if not points:
            return
        ns = floor(log10(len(points))) + 1
        positions.clear()
        for i, pt in enumerate(points):
            line = f.copyLine()
            unit = ENEMYPOSITION(line, self.mapGrid)
            unit.X, unit.Y = pt
            num = str(i+1).rjust(ns, '0') # Start from 1
            unit.name = f"{name}{num}"
            positions.append(unit)
            gimmicks.append(line)
        if friends:
            for f in friends:
                f.deleteLine()
            for p in positions:
                line = f.copyLine()
                line.setArg(1, p.name)

    def copyArgs(self, lineSrc, lineDst, idx):
        while lineDst:
            dst = lineDst.pop()
            dst.deleteLine()
        for src in lineSrc:
            line = dst.copyLine()
            arg = src.getArg(idx)
            line.setArg(idx, arg)
            lineDst.append(line)

    # Used for reinforcements
    def setWaki(self, f, pt):
        d = self.mapGrid.dirToCenter(pt)
        f.setArg(2, float(pt[0]))
        f.setArg(3, float(pt[1]))
        f.setArg(4, d)

    def _nearestNeighbor(self, neighbors, x, y):
        idx = 0
        dist2 = 1e9
        for i, n in enumerate(neighbors):
            d2 = (n.X - x)**2 + (n.Y - y)**2
            if d2 < dist2:
                dist2 = d2
                idx = i
        return neighbors[idx]


class MS01_X01(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms01_x01_battle_01', 1)

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 11))

        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[0].getArg(1) == 'UNIT_MASTER_CH_P014'
        funcs[0].setArg(2, 'AI_FREE')
        assert funcs[2].getArg(1) == 'DAG1'
        funcs[2].setArg(2, 'AI_FREE')
        assert funcs[4].getArg(1) == 'DAG3'
        funcs[4].setArg(2, 'AI_FREE')
        assert funcs[6].getArg(1) == 'CLB1'
        funcs[6].setArg(2, 'AI_FREE')

        # Assign PC positions
        candidates = sorted(vacant)
        n_pc = len(self.pcPositions)
        points = set()
        while len(points) < 10:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(5, 10)
            rect = self.mapGrid.randomRectangle(pt, n, candidates, d=3)
            points.update(rect)
            if len(points) > 20:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=4)
        vacant = vacant.difference(points).difference(outline)

        # Assign enemy positions
        candidates = sorted(vacant)
        n_enem = len(self.enemyPositions)
        points = set()
        while len(points) < 30:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(10, 15)
            rect = self.mapGrid.randomRectangle(pt, n, candidates, d=3)
            points.update(rect)
            if len(points) > 40:
                points = set()
        self.setPositions(points, self.enemyPositions)
        vacant = vacant.difference(points)

        self.setPCDirections()
        self.setEnemyDirections()


class MS02_X02(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms02_x02_battle_01', 1, 'ms02_x02_battle_1A_S')

    # DGRID spec everywhere except PC starting positions
    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getValid())

        # Set all tiles to DGRID
        self.mapGrid.clearSpecs('DGRID')
        self.mapGrid.addSpec('DGRID', vacant)

        # Set all AI to free by default
        for funcs in self.battle.getLocalFunction('ChangeAISettings'):
            for f in funcs:
                f.setArg(2, 'AI_FREE')

        # Start with PCs
        candidates = sorted(vacant)
        while True:
            while True:
                pt = random.sample(candidates, 1)[0]
                pcGrid = self.mapGrid.randomWalk(pt, len(vacant)//3)
                if len(pcGrid) == len(vacant)//3:
                    break
            points = set()
            while len(points) < len(self.pcPositions):
                pt = random.sample(pcGrid, 1)[0]
                n = random.randint(2, len(self.pcPositions))
                rect = self.mapGrid.randomRectangle(pt, n, pcGrid)
                points.update(rect)
            outline = self.mapGrid.outlineGrid(points, candidates, length=2)
            numOpen = len(vacant) - len(outline) - len(points)
            if numOpen >= 2*len(self.enemyPositions):
                break
        self.setPlayerPositions(points)
        vacant = vacant.difference(pcGrid).difference(outline)

        # Then do enemies
        self.setPositions(vacant, self.enemyPositions)

        self.setPCDirections()
        self.setEnemyDirections()


class MS03_X03(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms03_x03_battle_01', 1)

        self.ally = self.enemyPositions.pop(0)

        self.sld1 = self.enemyPositions[0]
        self.sld2 = self.enemyPositions[1]
        self.swd1 = self.enemyPositions[2]
        self.swd2 = self.enemyPositions[3]
        self.swd3 = self.enemyPositions[4]
        self.swd4 = self.enemyPositions[5]
        self.swd7 = self.enemyPositions[6]
        self.swd8 = self.enemyPositions[7]
        self.swd9 = self.enemyPositions[8]
        self.swd10 = self.enemyPositions[9]
        self.swd11 = self.enemyPositions[10]
        self.bow4 = self.enemyPositions[11]

        self.enemiesAnywhere = [
            self.sld1, self.sld2,
            self.swd1, self.swd2, self.swd3, self.swd4,
            self.swd7, self.swd8, self.swd9, self.swd10,
            self.swd11,
        ]

        self.ai_yanekeep = [self.bow4]
        self.ai_ukai = [self.swd4]

        self.aiYaneKeepMov = 41

    def update(self):
        super().update()

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 16))

        # Clear useless specs to help with selecting points
        self.mapGrid.clearSpecs('EV_KEIKAI') # Only used in ms19r_x44_battle_01
        self.mapGrid.clearSpecs('EV_ATKL') # Only used in ms19r_x44_battle_01
        self.mapGrid.clearSpecs('EV_TOWER') # Only used in ms19r_x44_battle_01
        self.mapGrid.clearSpecs('EV_ATKR') # Only used in ms19r_x44_battle_01
        self.mapGrid.clearSpecs('DGRID') # No unit changes AI with DGRID

        # Set default AIs
        aiSettings = self.battle.getLocalFunction('ChangeAISettings')
        funcs = aiSettings[0]
        assert funcs[0].getArg(1) == 'UNIT_MASTER_CH_N106'
        funcs[0].setArg(2, 'AI_FREE')
        assert funcs[5].getArg(1) == 'SWD4'
        funcs[5].setArg(2, 'AI_FREE')

        # Pick archer point first
        while True:
            dh, pt = self.mapGrid.randomHighPoint()
            g_pt = self.mapGrid.reachableLowGroundPoint(pt, target_change=dh) # g_pt is ensured to be a valid point
            if g_pt:
                path = self.mapGrid.shortestPath(pt, g_pt)
                grid = self.mapGrid.gridSameHeight(pt, tol=2)
                if path:
                    grid += path
                grid = list(set(grid)) # Filter repeats
                self.setAIMoveGrid(self.aiYaneKeepMov, grid)
                self.bow4.X, self.bow4.Y = g_pt
                vacant.remove(g_pt)
                break

        # Build a cluster of enemies nearby the archer at lower ground
        n_enem = len(self.enemiesAnywhere)
        enemyPoints = set()
        tol = 0
        candidates = sorted(vacant)
        while True:
            d = random.randint(5, 10)
            pt = self.mapGrid.randomNearbyPoint(g_pt, d, candidates, tol=tol)
            tol += 1
            if pt is None:
                continue
            n = random.randint(n_enem, 2*n_enem)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            enemyPoints.update(rect)
            if len(enemyPoints) >= 4*n_enem:
                break
        self.setPositions(enemyPoints, self.enemiesAnywhere)
        vacant = vacant.difference(enemyPoints)

        # Ensure pcs aren't too close to enemies
        nmPts = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPts, vacant, length=1)
        vacant = vacant.difference(outline)

        # Add PCs somewhere near/overlapping with these enemy clusters
        # If PC cluster(s) are picked completely randomly they could all
        # start on the other side of the map. Not interesting!!!!
        n_pc = len(self.pcPositions)
        points = set()
        candidates = sorted(vacant)
        refPoints = sorted(enemyPoints)
        while True:
            d = random.randint(5, 10)
            refPt = random.sample(enemyPoints, 1)[0]
            pt = self.mapGrid.randomNearbyPoint(refPt, d, candidates, tol=tol)
            tol += 1
            if pt is None:
                continue
            n = random.randint(4, 8)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) >= 12:
                break
        self.setPlayerPositions(points, ally=self.ally)
        vacant = vacant.difference(points)

        # Finalize directions of placed units
        self.setPCDirections(self.ally)
        self.setEnemyDirections()


class MS03_X04(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms03_x04_battle_01', 1)

        self.exharme = self.enemyPositions.pop(0)

        plinius = self.enemyPositions[0] # AI_BOSS -> AI_BOSS1 -> AI_BOSS2 -> AI_BOSS3
        bok1 = self.enemyPositions[1] # AI_DEF -> AI_FREE -> AI_BOSS2 -> AI_BOSS3
        bok2 = self.enemyPositions[2] # AI_DEF -> AI_FREE -> AI_BOSS2 -> AI_BOSS3
        bok3 = self.enemyPositions[3] # AI_HASIRA -> AI_FREE -> AI_BOSS2 -> AI_BOSS3
        bok4 = self.enemyPositions[4]
        bok5 = self.enemyPositions[5]
        bok6 = self.enemyPositions[6] # AI_NOMOVE -> AI_FREE -> AI_BOSS2 -> AI_BOSS3
        rod1 = self.enemyPositions[7] # AI_DEF -> AI_FREE -> AI_BOSS2 -> AI_BOSS3
        rod2 = self.enemyPositions[8] # AI_DEF -> AI_FREE -> AI_BOSS2 -> AI_BOSS3

        self.boss = [plinius]
        self.aiDef = [bok1, bok2, rod1, rod2]
        self.aiRest = [bok3, bok4, bok5, bok6]

        self.aiHasiraMov = 38
        self.aiNoMov = 36
        self.aiDefMov = 35
        self.aiBossMov = 37
        self.aiBoss1Mov = 40
        self.aiBoss2Mov = 39
        self.aiBoss3Mov = 42

    def update(self):
        super().update()

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 0))

        self.mapGrid.clearSpecs('ChangeBossAI_01')
        self.mapGrid.clearSpecs('ChangeBossAI_02')

        self.mapGrid.clearSpecs('DGRID1')
        self.mapGrid.clearSpecs('DGRID2')
        self.mapGrid.clearSpecs('DGRID3')

        # Set default AIs
        aiSettings = self.battle.getLocalFunction('ChangeAISettings')
        funcs = aiSettings[0]
        assert funcs[6].getArg(1) == 'BOK3'
        funcs[6].setArg(2, 'AI_FREE')
        assert funcs[7].getArg(1) == 'BOK6'
        funcs[7].setArg(2, 'AI_FREE')

        # Make DGRID1
        point = random.sample(vacant, 1)[0]
        dgrid1 = self.mapGrid.bfs(point, len(vacant)*2//3, vacant)
        self.mapGrid.addSpec('DGRID1', dgrid1)

        # AI_DEF is subset of DGRID1
        point = random.sample(dgrid1, 1)[0]
        ai_def = self.mapGrid.bfs(point, len(dgrid1)*2//3, dgrid1)
        self.setAIMoveGrid(self.aiDefMov, ai_def)

        # AI_BOSS is subset of AI_DEF
        point = random.sample(ai_def, 1)[0]
        ai_boss = self.mapGrid.bfs(point, len(ai_def)//3, ai_def)
        self.setAIMoveGrid(self.aiBossMov, ai_boss)

        # AI_BOSS1 is cluster near AI_BOSS
        while True:
            point = random.sample(ai_boss, 1)[0]
            ai_boss1 = self.mapGrid.nearbyCluster(point, 10, len(ai_boss), set(dgrid1).difference(ai_boss))
            if ai_boss1:
                break
        self.setAIMoveGrid(self.aiBoss1Mov, ai_boss1)

        # AI_BOSS2 is cluster near AI_BOSS1
        while True:
            point = random.sample(ai_boss1, 1)[0]
            ai_boss2 = self.mapGrid.nearbyCluster(point, 10, len(ai_boss1), set(dgrid1).difference(ai_boss1))
            if ai_boss2:
                break
        self.setAIMoveGrid(self.aiBoss2Mov, ai_boss2)

        # AI_BOSS3 is a superset of AI_BOSS2
        point = self.mapGrid.clusterMean(ai_boss2)
        ai_boss3 = self.mapGrid.bfs(point, len(ai_boss2)*2, dgrid1)
        self.setAIMoveGrid(self.aiBoss3Mov, ai_boss3)

        # Set dgrids
        pt1 = self.mapGrid.clusterMean(ai_boss1)
        dgrid2 = self.mapGrid.bfs(pt1, 2*len(ai_boss1), vacant)
        self.mapGrid.addSpec('DGRID2', dgrid2)
        self.mapGrid.addSpec('DGRID3', ai_boss2)

        # Set initial points for enemies
        enemyPoints = set()

        candidates = sorted(set(ai_def).difference(ai_boss).difference(enemyPoints))
        point = random.sample(candidates, 1)[0]
        self.setPositions([point], self.boss)
        enemyPoints.add(point)

        candidates = sorted(set(ai_def).difference(enemyPoints))
        points = random.sample(candidates, len(self.aiDef))
        self.setPositions(points, self.aiDef)
        enemyPoints.update(points)

        candidates = sorted(set(dgrid1).difference(enemyPoints))
        points = random.sample(candidates, len(self.aiRest))
        self.setPositions(points, self.aiRest)
        enemyPoints.update(points)

        # Prep for PCs
        vacant = set(vacant).difference(dgrid1)

        # Ensure pcs aren't too close to enemies
        nmPts = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPts, vacant, length=1)
        vacant = vacant.difference(outline)

        # Pick some clusters for PCs
        candidates = sorted(vacant)
        points = set()
        while len(points) < 12:
            pt = random.sample(candidates, 1)[0]
            cluster = self.mapGrid.randomCluster(5, candidates)
            points.update(cluster)
        vacant = vacant.difference(points)
        self.setPlayerPositions(points, ally=self.exharme)

        self.setPCDirections(allies=self.exharme)
        self.setEnemyDirections()


class MS04_X05(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms04_x05_battle_01', 1)
        self.dragan = self.enemyPositions.pop(0) # AI_TR1 -> AI_TR2 (on team count 1)
        self.pcPositions.append(self.dragan)

        self.sld1 = self.enemyPositions[0]
        self.rod1 = self.enemyPositions[1]
        self.bok1 = self.enemyPositions[2]
        self.bow3 = self.enemyPositions[3] # AI_DF -> AI_TR2 (on team count 1)
        self.swd1 = self.enemyPositions[4]
        self.swd2 = self.enemyPositions[5]
        self.bow1 = self.enemyPositions[6]
        self.swd5 = self.enemyPositions[7]
        self.sld2 = self.enemyPositions[8]
        self.bow2 = self.enemyPositions[9] # AI_SNP
        self.swd4 = self.enemyPositions[10]
        self.swd6 = self.enemyPositions[11]
        self.sld3 = self.enemyPositions[12]

        self.enemiesAnywhere = [self.sld1, self.rod1, self.bok1,
                                self.swd1, self.swd2, self.bow1,
                                self.swd5, self.sld2, self.swd4,
                                self.swd6, self.sld3]

        self.aiTR1Mov = 24
        self.aiTR2Mov = 26
        self.aiSNPMov = 25
        self.aiDFMov = 23

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getValid())

        # Setup aiTR1
        while True:
            edgePoint = self.mapGrid.randomEdgePoint()
            if edgePoint:
                break
        aiTR1 = self.mapGrid.bfs(edgePoint, 53, vacant)

        # Setup "BUFFER" outside but touching aiTR1
        outline = self.mapGrid.outlineGrid(aiTR1, vacant, length=1)
        pt = random.sample(outline, 1)[0]
        candidates = vacant.difference(aiTR1)
        bfr = self.mapGrid.bfs(pt, 10, candidates)
        # tmp = self.mapGrid.bfs(edgePoint, 1, candidates)[0]
        # bfr = self.mapGrid.bfs(tmp, 10, candidates)
        vacant = vacant.difference(bfr)

        # AI_DF and AI_TR2
        candidates = vacant.difference(aiTR1)
        pt = random.sample(bfr, 1)[0]
        count = 0
        while True:
            count += 1
            start = self.mapGrid.randomNearbyPoint(pt, 4, candidates, dh=2+count//30, tol=count//10)
            if start:
                aiTR2 = self.mapGrid.bfs(start, 100, candidates)
                if len(aiTR2) > 80:
                    break
        aiDF = aiTR2
        pt = random.sample(aiDF, 1)[0]
        self.bow3.X, self.bow3.Y = pt
        outline = self.mapGrid.outlineGrid([pt], vacant, length=1)
        vacant = vacant.difference(outline)
        if pt in vacant:
            vacant.remove(pt)

        # AI_SNP
        _, pt = self.mapGrid.randomHighPoint(candidates=vacant)
        aiSNP = self.mapGrid.bfs(pt, 6, vacant)
        vacant = vacant.difference(aiSNP) # ENSURE NOBODY ENDS UP IN THESE POINTS
        pt = random.sample(aiSNP, 1)[0] # Already removed from vacant
        self.bow2.X, self.bow2.Y = pt
        outline = self.mapGrid.outlineGrid([pt], vacant, length=1)
        vacant = vacant.difference(outline)
        if pt in vacant:
            vacant.remove(pt)

        # Pick and set PC points and remove from vacant
        pt = random.sample(bfr, 1)[0]
        while True:
            cluster = self.mapGrid.nearbyCluster(pt, 10, 5, vacant, dh=20)
            if cluster and len(cluster) >= 5:
                break
        points1 = random.sample(cluster, 3)
        vacant = vacant.difference(points1)

        # Other clusters
        n_pc = len(self.pcPositions)
        while True:
            points2 = set()
            while len(points2) < 8:
                cluster = self.mapGrid.randomCluster(5, vacant)
                if len(cluster) > 2:
                    points2.update(cluster)
            if len(points2) < 15:
                break
        vacant = vacant.difference(points2)

        # Set PC points
        points = set(points1).union(points2)
        self.setPlayerPositions(points, ally=self.dragan)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(outline)

        # Set the rest of the enemies
        vacant = vacant.difference(aiTR1)
        n_enem = len(self.enemyPositions)
        points = set()
        while len(points) < 3*n_enem:
            points.update(self.mapGrid.randomCluster(n_enem, vacant))
        self.setPositions(points, self.enemiesAnywhere)

        # Set directions
        self.setPCDirections(allies=self.dragan)
        self.setEnemyDirections()

        # Set AI
        self.setAIMoveGrid(self.aiTR1Mov, aiTR1)
        self.setAIMoveGrid(self.aiTR2Mov, aiTR2)
        self.setAIMoveGrid(self.aiDFMov, aiDF)
        self.setAIMoveGrid(self.aiSNPMov, aiSNP)


class MS05_X06(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms05_x06_battle_01', 1, 'ms05_x06_battle_S.lub')
        self.lub_before = Lub(pak, 'ms05_x06_research_01_before.lub') # Removes barracks
        self.lub_change = Lub(pak, 'ms05_x06_research_01_change_map.lub') # Removes barracks

        bow1 = self.enemyPositions[0] # Front_Archer
        bow6 = self.enemyPositions[1] # Scaffold
        sld1 = self.enemyPositions[2] # Guardian -> Normal (kill barricades 1, 2, 3, or 4)
        swd1 = self.enemyPositions[3] # Square
        swd2 = self.enemyPositions[4] # Square
        sld2 = self.enemyPositions[5] # Guardian -> Normal (kill barricades 1, 2, 3, or 4)
        bow5 = self.enemyPositions[6] # Scaffold

        bow6.wontMove()
        bow5.wontMove()

        self.enemiesSquare = [
            swd1, swd2, sld1, sld2, bow1
        ]

        wakis = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        self.wakisInvasionLine2 = [wakis[9], wakis[11], wakis[10], wakis[12]] # EnemyGen 6, 8, 7, 9
        self.wakisInvasionLine4 = [wakis[0], wakis[1], wakis[2]] # EnemyGen 1, 2, 3
        self.wakisInvasionLine5 = [wakis[3], wakis[4], wakis[5], wakis[6], wakis[7], wakis[8]]

        self.aiScaffoldMov = 44
        self.aiSquareMov = 43
        self.aiEntranceMov = 38
        self.aiFrontArcherMov = 39
        self.aiGuardianMov = 40
        self.aiArcherMov = 37

    def update(self):
        super().update()
        if self.isRandomized:
            self.lub_before.update()
            self.lub_change.update()

    def random(self):
        self.isRandomized = True
        targetPoint = (13, 25)
        vacant = set(self.mapGrid.getAccessible(*targetPoint)).difference([
            (0, 11), # Crate
            (9, 19), # Ladder
            (17, 19), # Ladder
        ])
        # Keep bows in same spots
        vacant = vacant.difference([
            (17, 18), (9, 18)
        ])

        # Remove need for changing Guardian AI
        # and careful placement of barricks 1-4
        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[0].getArg(2) == 'Front_Archer'
        funcs[0].setArg(2, 'Normal')
        assert funcs[1].getArg(2) == 'Guardian'
        funcs[1].setArg(2, 'Normal')
        assert funcs[2].getArg(2) == 'Square'
        funcs[2].setArg(2, 'Normal')
        assert funcs[3].getArg(2) == 'Square'
        funcs[3].setArg(2, 'Normal')
        assert funcs[4].getArg(2) == 'Guardian'
        funcs[4].setArg(2, 'Normal')

        # Setup Goal
        self.mapGrid.clearSpecs('Goal')
        while True:
            pt = self.mapGrid.randomEdgePoint(grid=vacant)
            if pt is None:
                continue
            goalGrid = self.mapGrid.randomRectangle(pt, 10, vacant)
            if len(goalGrid) > 5 and len(goalGrid) < 12:
                break
        self.mapGrid.addSpec('Goal', goalGrid)
        goalPoint = random.sample(goalGrid, 1)[0]

        # Barracks

        # Add barracks and filter out vacant
        barricadeGimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        barricadeGimmicks.pop() # Omit CONTAINER3
        barricadePositions = [ENEMYPOSITION(b, self.mapGrid) for b in barricadeGimmicks]

        # Surround goal with barracks
        goalBarracks = self.mapGrid.outlineGrid(goalGrid, vacant, length=1)
        random.shuffle(goalBarracks)

        # Ensure a fair chunk of the map is still accessible for reinforcements
        candidates = sorted(vacant.difference(goalGrid))
        while True:
            barrackLines = []
            while len(barrackLines) < len(barricadePositions) - 10:
                line = self.mapGrid.flatLine(candidates)
                if len(line) < 15:
                    barrackLines += line
            g = set(candidates).difference(barrackLines)
            for refPt in goalBarracks:
                accessibleAfterBarracks = self.mapGrid.getAccessible(*refPt, grid=g)
                ratio = float(len(accessibleAfterBarracks)) / len(g)
                if ratio > 0.7:
                    goalBarracks.remove(refPt)
                    break
            else:
                continue
            break
        self.setGimmickPositions(goalBarracks + barrackLines, barricadeGimmicks, barricadePositions)
        vacant = vacant.difference(goalBarracks)
        vacant = vacant.difference(barrackLines)
        accessibleAfterBarracks = accessibleAfterBarracks.intersection(vacant)

        # Spec grids
        self.mapGrid.clearSpecs('Front_Goal')
        self.mapGrid.clearSpecs('invasionLine1')
        self.mapGrid.clearSpecs('invasionLine2')
        self.mapGrid.clearSpecs('invasionLine3')
        self.mapGrid.clearSpecs('invasionLine4')
        self.mapGrid.clearSpecs('invasionLine5')
        self.mapGrid.clearSpecs('Justice_Surveillance')
        self.mapGrid.clearSpecs('Center_Line')

        def makeGrid(n):
            while True:
                outline = self.mapGrid.outlineGrid(goalGrid, vacant, length=n)
                avail = vacant.difference(goalGrid).difference(outline)
                if len(avail) > 30:
                    break
                n -= 1
            return outline

        frontGoalGrid = makeGrid(4)
        invasionLine5 = makeGrid(7)
        invasionLine4 = makeGrid(9)
        invasionLine3 = makeGrid(12)
        invasionLine2 = makeGrid(15)
        invasionLine1 = makeGrid(18)
        centerLine    = makeGrid(17)
        justiceServ   = makeGrid(11)

        self.mapGrid.addSpec('Front_Goal', frontGoalGrid)
        self.mapGrid.addSpec('invasionLine5', invasionLine5)
        self.mapGrid.addSpec('invasionLine4', invasionLine4)
        self.mapGrid.addSpec('invasionLine3', invasionLine3)
        self.mapGrid.addSpec('invasionLine2', invasionLine2)
        self.mapGrid.addSpec('invasionLine1', invasionLine1)
        self.mapGrid.addSpec('Center_Line', centerLine)
        self.mapGrid.addSpec('Justice_Surveillance', justiceServ)

        # Reinforcements
        def setPoints(points, funcs):
            for p, f in zip(points, funcs):
                self.setWaki(f, p)
        
        inv4 = random.sample(goalGrid, len(self.wakisInvasionLine4))
        setPoints(inv4, self.wakisInvasionLine4)

        inv2 = set()
        count = 0
        while len(inv2) < len(self.wakisInvasionLine2):
            d = random.randint(10, 15)
            cluster = self.mapGrid.nearbyCluster(goalPoint, d, 3, accessibleAfterBarracks, dh=5, tol=count//10)
            count += 1
            if cluster is None:
                continue
            inv2.update(cluster)
        setPoints(inv2, self.wakisInvasionLine2)

        inv5 = set()
        count = 0
        while len(inv5) < len(self.wakisInvasionLine5):
            d = random.randint(10, 15)
            cluster = self.mapGrid.nearbyCluster(goalPoint, d, 3, accessibleAfterBarracks, dh=5, tol=count//10)
            count += 1
            if cluster is None:
                continue
            inv5.update(cluster)
        setPoints(inv5, self.wakisInvasionLine5)

        reinforcePoints = set(inv2).union(inv4).union(inv5)
        self.mapGrid.clearSpecs('Reinforce')
        self.mapGrid.addSpec('Reinforce', reinforcePoints)

        # Set enemies and square ai grid
        pt1 = (13, 13)
        pt2 = (13, 19)
        pt = self.mapGrid.clusterMean(goalGrid)
        d1 = self.mapGrid.distance(pt, pt1)
        d2 = self.mapGrid.distance(pt, pt2)
        if d1 < d2:
            rectAIGrid = [(i,j) for i in range(6, 21) for j in range(9, 23)]
        else:
            rectAIGrid = [(i,j) for i in range(6, 21) for j in range(19, 35)]

        candidates = sorted(vacant.intersection(rectAIGrid))
        self.setPositions(candidates, self.enemiesSquare)
        vacant = vacant.difference(rectAIGrid)

        # Ensure pcs aren't too close to enemies
        nmPts = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPts, vacant, length=1)
        vacant = vacant.difference(outline)

        # Set PCs
        pcPt = self.mapGrid.greatestDistance(goalPoint)
        candidates = vacant.difference(goalGrid).difference(invasionLine1)
        points = set()
        count = 0
        while len(points) < 12:
            while True:
                pt = self.mapGrid.randomNearbyPoint(pcPt, 10, candidates, tol=count//20)
                count += 1
                if pt:
                    break
            n = random.randint(4, 10)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 20:
                points = set()
        self.setPlayerPositions(points)
        vacant = vacant.difference(points)

        # Set directions
        self.setPCDirections()
        self.setEnemyDirections()

        # Set AI grid changes
        self.setAIMoveGrid(self.aiEntranceMov, goalGrid + frontGoalGrid)
        self.setAIMoveGrid(self.aiSquareMov, rectAIGrid)

        # Overview
        goalPt = self.mapGrid.clusterMean(goalGrid)
        f = self.battle.getLocalFunction('ChangeStageCameraToMapGrid')[0]
        f.setArg(1, float(goalPt[0]))
        f.setArg(2, float(goalPt[1]))


class MS06_X07(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms06_x07_battle_01', 1, 'ms06_x07_battle_S')

        self.switch = ENEMYPOSITION(self.battleCommon.getLocalFunction('CreateGimmickData')[0], self.mapGrid)
        self.maxwell = self.enemyPositions.pop(0)

        self.spawns = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        self.spawnsGroup1 = self.spawns[:2]
        self.spawnsGroup2 = self.spawns[2:8]
        self.spawnsGroup3 = self.spawns[8:]

        bow1 = self.enemyPositions[0] # Archer -> Archer (no change?)
        swd3 = self.enemyPositions[1]
        swd5 = self.enemyPositions[2]
        swd6 = self.enemyPositions[3]
        bow4 = self.enemyPositions[4]
        guardian = self.enemyPositions[5] # Guardian -> Normal
        bow3 = self.enemyPositions[6] # Sniper
        bow2 = self.enemyPositions[7] # Sniper
        swd1 = self.enemyPositions[8] # Bridge
        swd2 = self.enemyPositions[9] # Bridge

        bow2.wontMove()
        bow3.wontMove()

        self.enemiesSwitch = [bow1, guardian]
        self.swdBridge = [swd1, swd2]
        self.sniper = [bow3, bow2] # Don't change!
        self.enemiesAnywhere = [swd3, swd5, swd6, bow4]

        # Keep near switch with archer subset of guardian
        self.aiArcherMove = 34
        self.aiGuardianMove = 33

        # Keep Maxwell near enemy spawns
        self.aiMaxwellMove = 32
        self.aiMaxwellAtk = 25



    def random(self):
        self.isRandomized = True
        self.mapGrid.clearSpecs('BridgeSide02')
        self.mapGrid.clearSpecs('CastleSIde')
        self.mapGrid.clearSpecs('CastleSIde02')
        self.mapGrid.clearSpecs('ChangeAI_01')
        self.mapGrid.clearSpecs('ChangeAI1')
        self.mapGrid.clearSpecs('ChangeAI2')
        self.mapGrid.clearSpecs('ChangeAI3')
        self.mapGrid.clearSpecs('ChangeAI_BSide')
        self.mapGrid.clearSpecs('ChangeAI_CSide')
        self.mapGrid.clearSpecs('ChangeAI_Mob1')
        self.mapGrid.clearSpecs('ChangeAI_Mob2')
        self.mapGrid.clearSpecs('Goal2')
        self.mapGrid.clearSpecs('None')
        self.mapGrid.clearSpecs('Reinforce')
        self.mapGrid.clearSpecs('Reinforce_sqex04_01')
        self.mapGrid.clearSpecs('Reinforce_sqex04_02')

        # Split grid into chunks to be used
        grid = self.mapGrid.getValid()
        vacant = set(filter(lambda x: x[0] < 16, grid))
        vacantBridge = set(filter(lambda x: x[0] > 16 and x[0] < 32, grid))
        if random.random() < 0.5:
            bridge = self.mapGrid.bfs((10, 10), 1000, vacant)
            castleSide = set(filter(lambda x: x[0] > 24 and x[0] < 32, vacantBridge))
            self.mapGrid.clearSpecs('Bridge')
            self.mapGrid.addSpec('Bridge', bridge)
            # self.mapGrid.clearSpecs('CastleSide')
            # self.mapGrid.addSpec('CastleSide', castleSide)
            vacant = vacantBridge
            vacantBridge = bridge
        else:
            bridge = self.mapGrid.getIdxs('Bridge')

        # Filter out sniper outlines to make sure no enemies overlap
        for enemy in self.sniper:
            grid = [(enemy.X, enemy.Y)]
            vacant = vacant.difference(grid)
            bridge = list(filter(lambda x: x not in grid, bridge))

        ##########
        # SWITCH #
        ##########

        # Candidates for the switch
        notAllowed = [
            # Ladders            
            (8,9),(8,18),(13,10),(13,17),(8,10),(8,17),(14,10),(14,17),
            # Cannot pass            
            (1,8),(2,8),(4,8),(5,8),(8,8),(9,8),(1,19),
            (2,19),(4,19),(5,19),(8,19),(9,19),
            # Default spot for snipers
            (14,9),(14,18),
        ]
        candidates = sorted(vacant)

        # Set switch and nearby enemies
        while True:
            pt = random.sample(candidates, 1)[0]
            switchGrid = self.mapGrid.randomRectangle(pt, 8, vacant)
            allowedGrid = list(filter(lambda x: x not in notAllowed, switchGrid))
            if len(switchGrid) > 6 and allowedGrid:
                break

        switchPoint = random.sample(allowedGrid, 1)[0]
        self.mapGrid.clearSpecs('Switch')
        self.mapGrid.addSpec('Switch', [switchPoint])
        self.switch.X, self.switch.Y = switchPoint
        switchGrid.remove(switchPoint)

        self.setPositions(switchGrid, self.enemiesSwitch)
        self.setAIMoveGrid(self.aiArcherMove, switchGrid)
        self.setAIMoveGrid(self.aiGuardianMove, switchGrid)

        vacant = vacant.difference(switchGrid)
        vacant.remove(switchPoint)

        # Set the camera for the overview
        camera = self.battle.getLocalFunction('ChangeStageCameraToMapGrid')[1]  # in function FieldInfo
        if self.switch.Y < 10:
            a = [270.0, 315.0, 315.0]
            for i, c in enumerate(camera[:3]):
                ct = c.getArg(8)
                t = ct.getTable()[0]
                t['Yaw'] = a[i]
                ct.setTable(t)
        camera[1].setArg(1, float(switchPoint[0]))
        camera[1].setArg(2, float(switchPoint[1]))
        camera[2].setArg(1, float(switchPoint[0]))
        camera[2].setArg(2, float(switchPoint[1]))
        focusMapGrid = self.battle.getLocalTable('focusMapGrid')
        table = focusMapGrid.getTable()[0]
        table['X'] = float(switchPoint[0])
        table['Y'] = float(switchPoint[1])
        focusMapGrid.setTable(table)

        ##########
        # SPAWNS #
        ##########

        def setAllWaki(funcs, points):
            for f, p in zip(funcs, points):
                self.setWaki(f, p)

        while True:
            points1 = self.mapGrid.randomWalkGrid(len(self.spawnsGroup1), vacant)
            if points1:
                break
        setAllWaki(self.spawnsGroup1, points1)

        while True:
            points2 = self.mapGrid.randomWalkGrid(len(self.spawnsGroup2), vacant)
            if points2:
                break
        setAllWaki(self.spawnsGroup2, points2)

        while True:
            points3 = self.mapGrid.randomWalkGrid(len(self.spawnsGroup3), bridge)
            if points3:
                break
        setAllWaki(self.spawnsGroup3, points3)

        reinforce = set(points1).union(points2).union(points3)
        self.mapGrid.clearSpecs('Reinforce')
        self.mapGrid.addSpec('Reinforce', reinforce)

        ############
        # THE REST #
        ############

        # Enemies
        points = set()
        while len(points) < 2*len(self.enemiesAnywhere):
            d = random.randint(1, 8)
            pt = self.mapGrid.randomNearbyPoint(switchPoint, d, vacant, dh=30)
            if pt in vacant:
                points.add(pt)
                vacant.remove(pt)
        self.setPositions(points, self.enemiesAnywhere)

        points = random.sample(bridge, 2)
        self.setPositions(points, self.swdBridge)

        # Ensure pcs aren't too close to enemies
        nmPts = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPts, vacant, length=1)
        vacant = vacant.difference(outline)

        # PCs
        points = set()
        candidates = sorted(vacant)
        count = 0
        while len(points) < 10:
            pt = self.mapGrid.greatestDistance(switchPoint, grid=vacant, tol=count//10)
            pts = self.mapGrid.randomRectangle(pt, 10, candidates)
            points.update(pts)
            count += 1
        self.setPlayerPositions(points, ally=self.maxwell)
        outline = self.mapGrid.outlineGrid(points, vacant, length=1)
        vacant = vacant.difference(points).difference(outline)
        self.mapGrid.clearSpecs('CastleSide')
        self.mapGrid.addSpec('CastleSide', points)

        self.setPCDirections(allies=self.maxwell)
        self.setEnemyDirections()


# Battle in Wolfort against Avlora using fire
class MS07_X08(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms07_x08_battle_01', 0, 'ms07_x08_2b015')

        gimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        self.switchA = ENEMYPOSITION(gimmicks[0], self.mapGrid)
        self.switchB = ENEMYPOSITION(gimmicks[1], self.mapGrid)
        self.switchC = ENEMYPOSITION(gimmicks[2], self.mapGrid)
        self.switchD = ENEMYPOSITION(gimmicks[3], self.mapGrid)
        self.booths = [ENEMYPOSITION(g, self.mapGrid) for g in gimmicks[4:]]

        avlora = self.enemyPositions[0] # AISetting1 -> AISetting7 -> AISetting6
        bow1 = self.enemyPositions[1] # AISetting2 -> AISetting8
        bow2 = self.enemyPositions[2] # AISetting2 -> AISetting8
        bow3 = self.enemyPositions[3] # AISetting2 -> AISetting8
        sld1 = self.enemyPositions[4] # AISetting6
        swd3 = self.enemyPositions[5] # AISetting6
        bok1 = self.enemyPositions[6] # AISetting6
        sld3 = self.enemyPositions[7] # AISetting6
        bok2 = self.enemyPositions[8] # AISetting6
        swd1 = self.enemyPositions[9] # AISetting6
        assert len(self.enemyPositions) == 10

        self.boss = [
            avlora
        ]

        self.enemiesAnywhere = [
            sld1, swd3, bok1, sld3, bok2, swd1,
        ]

        self.bows = [
            bow1, bow2, bow3,
        ]

        self.aiSetting1 = 41
        self.aiSetting2 = 42
        self.aiSetting7 = 47

    def random(self):
        self.isRandomized = True
        accessible = self.mapGrid.getAccessible(0, 23)
        vacant = set(filter(lambda pt: pt[0] <= 20, accessible))
        stands = [
            (5,11), (6,11),
            (8,11), (9,11),
            (11,11), (12,11),
            (8,16), (9,16), (10,16), (11,16),
        ]
        impassable = [ # No clue why these tiles are impassbable
            (16,23), (17,23)
        ]
        vacant = vacant.difference(stands).difference(impassable)

        eventA = self.mapGrid.getIdxs('Event_A')
        eventB = self.mapGrid.getIdxs('Event_B')
        eventC = self.mapGrid.getIdxs('Event_C')
        eventD = self.mapGrid.getIdxs('Event_D')

        # Set switches
        candidates = sorted(vacant.difference(eventA).difference(eventB).difference(eventC).difference(eventD))
        outlineA = self.mapGrid.outlineGrid(eventA, candidates, length=4)
        outlineB = self.mapGrid.outlineGrid(eventB, candidates, length=4)
        outlineC = self.mapGrid.outlineGrid(eventC, candidates, length=4)
        outlineD = self.mapGrid.outlineGrid(eventD, candidates, length=4)
        while True:
            ptA = random.sample(outlineA, 1)[0]
            ptB = random.sample(outlineB, 1)[0]
            ptC = random.sample(outlineC, 1)[0]
            ptD = random.sample(outlineD, 1)[0]
            if len(set([ptA, ptB, ptC, ptD])) == 4:
                break
        self.switchA.X, self.switchA.Y = ptA
        self.switchB.X, self.switchB.Y = ptB
        self.switchC.X, self.switchC.Y = ptC
        self.switchD.X, self.switchD.Y = ptD
        vacant = vacant.difference([ptA, ptB, ptC, ptD])
        cameras = self.battleScene.getLocalFunction('ChangeStageCameraToMapGrid')[0]
        cursor = self.battleScene.getLocalFunction('MoveBattleCursor')
        def setSwitchOverview(pt, func):
            func.setArg(1, float(pt[0]))
            func.setArg(2, float(pt[1]))
        setSwitchOverview(ptB, cameras[0])
        setSwitchOverview(ptB, cameras[1])
        setSwitchOverview(ptB, cursor[0])
        setSwitchOverview(ptC, cameras[2])
        setSwitchOverview(ptC, cursor[1])
        setSwitchOverview(ptD, cameras[3])
        setSwitchOverview(ptD, cursor[2])
        setSwitchOverview(ptA, cameras[4])
        setSwitchOverview(ptA, cursor[3])

        # Set PCs
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            pcPoints = self.mapGrid.randomRectangle(pt, 15, candidates)
            if len(pcPoints) >= 15 and len(pcPoints) < 40:
                break
        self.setPlayerPositions(pcPoints)
        outline = self.mapGrid.outlineGrid(pcPoints, candidates)
        vacant = vacant.difference(pcPoints).difference(outline)

        # Set wakis
        candidates = sorted(vacant.difference(eventA).difference(eventB).difference(eventC).difference(eventD))
        edges = self.mapGrid.edgesOfGrid(candidates)
        points = random.sample(edges, 6)
        funcs = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        for p, f in zip(points, funcs):
            self.setWaki(f, p)

        # Set bow enemies
        roofs = self.mapGrid.filterTileTypes('roof')
        candidates = sorted(vacant.intersection(roofs))
        if len(candidates) < len(self.bows):
            candidates = sorted(vacant)
        points = random.sample(candidates, len(self.bows))
        self.setPositions(points, self.bows)
        vacant = vacant.difference(points)
        self.setAIMoveGrid(self.aiSetting2, roofs)

        # Set Avlora as far as possible from PCs
        pt = self.mapGrid.clusterMean(pcPoints)
        candidates = sorted(vacant.difference(eventA).difference(eventB).difference(eventC).difference(eventD))
        tol = 3
        while True:
            avPoint = self.mapGrid.greatestDistance(pt, grid=candidates, tol=tol)
            if avPoint:
                break
            tol += 1
        vacant.remove(avPoint)
        self.setPositions([avPoint], self.boss)
        setting1Grid = self.mapGrid.bfs(avPoint, 6, candidates)
        setting7Grid = list(filter(lambda pt: pt not in setting1Grid, self.mapGrid.bfs(avPoint, 20, candidates)))
        self.setAIMoveGrid(self.aiSetting1, setting1Grid)
        self.setAIMoveGrid(self.aiSetting7, setting7Grid)

        # Set enemies
        candidates = sorted(vacant)
        enemyPoints = set(self.mapGrid.randomRectangle(avPoint, 20, candidates))
        while len(enemyPoints) < 2*len(self.enemiesAnywhere):
            enemyPoints.update(self.mapGrid.outlineGrid(enemyPoints, candidates, length=1))
        self.setPositions(enemyPoints, self.enemiesAnywhere)
        vacant.difference(enemyPoints)

        # Finalize
        self.setPCDirections()
        self.setEnemyDirections()


# Battle at Falkes Streets
class MS07_X09(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms07_x09_battle_01', 0, 'ms07_x09_2b015')

        boss = self.enemyPositions[0]
        swd2 = self.enemyPositions[1]
        bow1 = self.enemyPositions[2]
        bow2 = self.enemyPositions[3]
        bok1 = self.enemyPositions[4]
        rod1 = self.enemyPositions[5]
        bok2 = self.enemyPositions[6]
        bow3 = self.enemyPositions[7]
        sld1 = self.enemyPositions[8]
        sld2 = self.enemyPositions[9]
        rod2 = self.enemyPositions[10]
        swd1 = self.enemyPositions[11]
        rod3 = self.enemyPositions[12]
        swd3 = self.enemyPositions[13]
        swd4 = self.enemyPositions[14]
        swd5 = self.enemyPositions[15]

        # Keep these enemies nearby
        self.bossCluster = [
            boss, rod2,
        ]

        # Literally place them anywhere
        self.enemiesAnywhere = [
            swd2, bow1, bow2, bok1, rod1, bok2, bow3,
            sld1, sld2, swd1, rod3, swd3, swd4, swd5,
        ]

        # NOTES
        # ai is designed to have archers and mages attack from afar (and high, but only important for archers)
        # set PCs as 2-3 smaller rectangles in a large rectangle, then place everyone else outside of that
        # Allow mages to attack from anywhere
        self.aiMagicMov = 14
        self.aiArcher2Mov = 13

        # Don't allow these points
        gimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        self.dontAllow = [ # Barricade and scarecrow points
            (g.getArg(3), g.getArg(4)) for g in gimmicks
        ]

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(3, 2))

        # Allow magic movement to anywhere
        self.setAIMoveGrid(self.aiMagicMov, vacant)

        # Place PCs
        candidates = sorted(vacant)
        points = set()
        while len(points) < 12:
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, 4, candidates)
            points.update(rect)
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Place boss group
        while True:
            cluster = self.mapGrid.randomCluster(10, vacant)
            if len(cluster) > 2*len(self.bossCluster):
                break
        self.setPositions(cluster, self.bossCluster)
        vacant = vacant.difference(cluster)

        # Place all other enemies
        self.setPositions(vacant, self.enemiesAnywhere)

        # Finalize
        self.setPCDirections()
        self.setEnemyDirections()


class MS08A_X10(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms08a_x10_battle_01', 0)

        self.gimmickLubs = [
            Lub(pak, "ms08a_x10_a2_0010.lub"),
            Lub(pak, "ms08a_x10_research_01_before.lub"),
            Lub(pak, "ms08a_x10_research_01_change_map.lub"),
            Lub(pak, "ms08a_x10_battle_01_after.lub"),
            Lub(pak, "ms08a_x10_battle_01_before.lub"),
        ]

        boss = self.enemyPositions[0]
        swd1 = self.enemyPositions[1]
        spr1 = self.enemyPositions[2]
        bow1 = self.enemyPositions[3]
        rod2 = self.enemyPositions[4]
        rod3 = self.enemyPositions[5]
        swd2 = self.enemyPositions[6]
        swd3 = self.enemyPositions[7]
        swd4 = self.enemyPositions[8]
        spr3 = self.enemyPositions[9]
        bow4 = self.enemyPositions[10]
        spr2 = self.enemyPositions[11]
        swd5 = self.enemyPositions[12]

        self.bossCluster = [
            boss, rod2, rod3,
        ]

        self.enemiesAnywhere = [
            swd1, spr1, swd2, swd3,
            swd4, spr3, bow4, spr2, swd5,
        ]

        self.enemyAISetting1Mov = bow1
        self.aiSetting1Mov = 25 # Only used for bow1

        self.grapeGimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        self.grapes = [ENEMYPOSITION(i, self.mapGrid) for i in self.grapeGimmicks] # All gimmicks here are grapes

    def update(self):
        super().update()
        if self.isRandomized:
            for lub in self.gimmickLubs:
                lub.update()

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 0))

        # Start with grapes - get various rectangles
        candidates = sorted(vacant)
        while True:
            points = set()
            while len(points) < 34:
                pt = random.sample(candidates, 1)[0]
                n = random.randint(4, 10)
                rect = self.mapGrid.randomRectangle(pt, n, candidates)
                points.update(rect)
            # Make sure grapes don't block of a giant chunk of the map!
            remaining = list(filter(lambda x: x not in points, candidates))
            start = random.sample(remaining, 1)[0]
            accessible = self.mapGrid.getAccessible(*start, grid=remaining)
            if len(accessible) > 0.8*len(vacant):
                break
        self.setGimmickPositions(points, self.grapeGimmicks, self.grapes)
        vacant = set(accessible)

        # Set bow1 and AI first
        candidates = sorted(vacant)
        dh, pt = self.mapGrid.randomHighPoint(candidates=candidates)
        ptNearbyArcher = self.mapGrid.reachableLowGroundPoint(pt, target_change=dh)
        setting1Grid = self.mapGrid.bfs(pt, 15, vacant)
        self.setAIMoveGrid(self.aiSetting1Mov, setting1Grid)
        highPoint = random.sample(setting1Grid, 1)[0]
        self.enemyAISetting1Mov.X = highPoint[0]
        self.enemyAISetting1Mov.Y = highPoint[1]
        outline = self.mapGrid.outlineGrid([highPoint], vacant)
        vacant = vacant.difference(setting1Grid).difference(outline)

        # Set first group below/near bow1
        points1 = set()
        candidates = sorted(vacant)
        if ptNearbyArcher:
            n = random.randint(4, 8)
            points1 = self.mapGrid.bfs(ptNearbyArcher, n, candidates)
        if not points1:
            while True:
                refPt = random.sample(setting1Grid, 1)[0]
                d = random.randint(8, 15)
                pt = self.mapGrid.randomNearbyPoint(refPt, d, candidates, dh=30)
                n = random.randint(4, 8)
                points1 = self.mapGrid.bfs(pt, n, candidates)
                if len(points1) > 3:
                    break
        vacant = vacant.difference(points1)
        points1 = sorted(points1)

        # Set remaining groups randomly
        points2 = set()
        candidates = sorted(vacant)
        count = 0
        while len(points2) < 10:
            d = random.randint(4, 15)
            refPt = random.sample(points1, 1)[0]
            pt = self.mapGrid.randomNearbyPoint(refPt, d, candidates, dh=30, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(4, 8)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            if len(rect) > 2 and len(rect) < 10:
                points2.update(rect)

        pcPoints = sorted(points2.union(points1))
        self.setPlayerPositions(pcPoints)
        outline = self.mapGrid.outlineGrid(pcPoints, vacant, length=1)
        vacant = vacant.difference(pcPoints).difference(outline)
        # Keep Serenoal and "Roland" right next to each other
        while True:
            pt = random.sample(pcPoints, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, 2, pcPoints)
            if len(rect) == 2:
                break
        self.setUnitTable(rect)

        # Set boss cluster
        candidates = sorted(vacant)
        count = 0
        while True:
            refPt = random.sample(pcPoints, 1)[0]
            pt = self.mapGrid.greatestDistance(refPt, tol=5+count//10)
            count += 1
            if pt not in vacant:
                continue
            bossGrid = self.mapGrid.randomRectangle(pt, 10, candidates)
            if len(bossGrid) > 2*len(self.bossCluster):
                break
        self.setPositions(bossGrid, self.bossCluster)
        outline = self.mapGrid.outlineGrid(bossGrid, candidates)
        vacant = vacant.difference(bossGrid).difference(outline)

        # Set remaining enemies
        candidates = sorted(vacant)
        points = set()
        count = 0
        while len(points) < 3*len(self.enemiesAnywhere):
            d = random.randint(10, 18)
            refPt = random.sample(pcPoints, 1)[0]
            pt = self.mapGrid.randomNearbyPoint(refPt, d, candidates, dh=30, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(1, 8)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesAnywhere)
        vacant = vacant.difference(points)

        self.setPCDirections()
        self.setEnemyDirections()

class MS08A_X11(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms08a_x11_battle_01', 0)

        self.gimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        self.barricades = [ENEMYPOSITION(i, self.mapGrid) for i in self.gimmicks]
        self.gimmickAI = self.battle.getLocalFunction('SetMapGimmickUnitCampForAI') # Need to update names

        boss = self.enemyPositions[0]
        rod1 = self.enemyPositions[1]
        swd1 = self.enemyPositions[2]
        swd2 = self.enemyPositions[3]
        spr1 = self.enemyPositions[4]
        sld1 = self.enemyPositions[5]
        sld2 = self.enemyPositions[6]
        sld3 = self.enemyPositions[7]
        bow1 = self.enemyPositions[8]
        bow3 = self.enemyPositions[9]
        bow4 = self.enemyPositions[10]
        bok1 = self.enemyPositions[11]
        bok2 = self.enemyPositions[12]

        self.leftAI = [
            swd1, bow3, bow4,
        ]

        self.rightAI = [
            swd2, sld3, bok1,
        ]

        self.centerAI = [
            bok2, bow1, spr1,
        ]

        self.bossCluster = [
            boss, rod1,
        ]

        self.enemiesRemaining = [
            sld1, sld2,
        ]

        self.aiSettingRightMov = 35
        self.aiSettingRightAtk = 28
        self.aiSettingLeftMov = 34
        self.aiSettingLeftAtk = 27
        self.aiSettingCenterMov = 33
        self.aiSettingCenterAtk = 26
        self.aiSettingBossMov = 37

    def random(self):
        self.isRandomized = True
        # Omit tiles with y coordinates of 0, 1, or 2
        accessible = self.mapGrid.getAccessible(8, 3)
        vacant = set(filter(lambda p: p[1] > 2, accessible))

        # Add to ai grids
        aiRightMov = set(self.getAIMoveGrid(self.aiSettingRightMov))
        aiRightAtk = set(vacant) #set(self.getAIAtkGrid(self.aiSettingRightAtk))
        aiLeftMov = set(self.getAIMoveGrid(self.aiSettingLeftMov))
        aiLeftAtk = set(vacant) #set(self.getAIAtkGrid(self.aiSettingLeftAtk))
        aiCenterMov = set(self.getAIMoveGrid(self.aiSettingCenterMov))
        aiCenterAtk = set(vacant) #set(self.getAIAtkGrid(self.aiSettingCenterAtk))

        for j in range(14, 17):
            for i in range(9):
                aiLeftMov.add((i, j))
                aiLeftAtk.add((i, j))
            for i in range(7, 16):
                aiRightMov.add((i, j))
                aiRightAtk.add((i, j))

        self.setAIMoveGrid(self.aiSettingRightMov, aiRightMov)
        self.setAIAtkGrid(self.aiSettingRightAtk, aiRightAtk)
        self.setAIMoveGrid(self.aiSettingLeftMov, aiLeftMov)
        self.setAIAtkGrid(self.aiSettingLeftAtk, aiLeftAtk)
        self.setAIAtkGrid(self.aiSettingCenterAtk, aiCenterAtk)

        # Set barricades
        points = set()
        ng = len(self.gimmicks)
        n = random.randint(ng-5, ng+5)
        while len(points) < n:
            line = self.mapGrid.flatLine(vacant)
            if len(line) < 6:
                points.update(line)
        self.setGimmickPositions(points, self.gimmicks, self.barricades)
        self.copyArgs(self.gimmicks, self.gimmickAI, 1)
        assert len(self.gimmicks) == len(points)
        assert len(self.gimmickAI) == len(points)
        vacant = vacant.difference(points)

        # Pick points
        while True:
            pcPoint = self.mapGrid.randomEdgePoint(grid=vacant)
            pcGrid = self.mapGrid.bfs(pcPoint, 17*16//4, vacant) # Maybe surround this grid with barracks?
            if len(pcGrid) < 50:
                continue

            outline = self.mapGrid.outlineGrid(pcGrid, vacant, length=1)
            tmpCand = vacant.difference(pcGrid).difference(outline)
            bossPoint = self.mapGrid.greatestDistance(pcPoint, grid=tmpCand)
            bossGrid = self.mapGrid.bfs(bossPoint, 9, tmpCand)
            if len(bossGrid) < 4:
                continue

            break

        # Set player starting positions
        points = set()
        while len(points) < 12:
            rect = self.mapGrid.randomCluster(4, pcGrid)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Set boss cluster
        self.setPositions(bossGrid, self.bossCluster)
        vacant = vacant.difference(bossGrid)

        # Set other groups
        rightGrid = aiRightMov.intersection(vacant)
        points = set()
        n = len(self.rightAI)
        while len(points) < 4*n:
            grid = self.mapGrid.randomCluster(n, rightGrid)
            points.update(grid)
        vacant = vacant.difference(points)
        self.setPositions(points, self.rightAI)

        leftGrid = aiLeftMov.intersection(vacant)
        points = set()
        n = len(self.leftAI)
        while len(points) < 4*n:
            grid = self.mapGrid.randomCluster(n, leftGrid)
            points.update(grid)
        vacant = vacant.difference(points)
        self.setPositions(points, self.leftAI)

        centerGrid = set(aiCenterMov).intersection(vacant)
        points = set()
        n = len(self.centerAI)
        while len(points) < 4*n:
            grid = self.mapGrid.randomCluster(n, centerGrid)
            points.update(grid)
        vacant = vacant.difference(points)
        self.setPositions(points, self.centerAI)

        self.setPositions(vacant, self.enemiesRemaining)

        self.setPCDirections()
        self.setEnemyDirections()


# Team up with Aesfrosti (Avlora et al) and fight Hyzantian (Booker et al)
class MS08B_X12(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms08b_x12_battle_01', 1)

        gbow3 = self.enemyPositions.pop()
        gbow2 = self.enemyPositions.pop()
        avlora = self.enemyPositions.pop()
        self.allies = [
            gbow3, gbow2, avlora,
        ]

        booker = self.enemyPositions[0] # Boss_Wait -> Normal
        bow1 = self.enemyPositions[1]
        bok1 = self.enemyPositions[2]
        rod1 = self.enemyPositions[3]
        bow2 = self.enemyPositions[4]
        bok2 = self.enemyPositions[5]
        rod2 = self.enemyPositions[6]
        swd1 = self.enemyPositions[7]
        swd2 = self.enemyPositions[8]
        dag1 = self.enemyPositions[9] # AI_Assassin
        rid4 = self.enemyPositions[10] # WaterWay -> Just set to Normal and skip this AI
        rid5 = self.enemyPositions[11] # Detour
        rid6 = self.enemyPositions[12] # Detour
        rid1 = self.enemyPositions[13] # Detour
        rid2 = self.enemyPositions[14] # Detour

        self.bossCluster = [
            booker, bok2, rod2,
        ]

        self.enemiesAnywhere = [
            bow1, bok1, rod1, bow2, swd1, swd2,
            dag1, rid4, rid5, rid6, rid1, rid2,
        ]


    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 11))

        # Change AI
        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[3].getArg(1) == 'RID4', funcs[3].getArg(1)
        funcs[3].setArg(2, 'Normal')

        # Puddles
        puddles = self.battleCommon.getLocalFunction('StartPuddle')
        points = set()
        candidates = sorted(vacant)
        while len(points) < len(puddles):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, 10)
            path = self.mapGrid.randomWalk(pt, n)
            points.update(path)
        for line in puddles:
            line.deleteLine()
        for x, y in points:
            newLine = line.copyLine()
            newLine.setArg(1, float(x))
            newLine.setArg(2, float(y))

        # Pick ally points
        candidates = sorted(vacant)
        n = len(self.allies)
        while True:
            pt = random.sample(candidates, 1)[0]
            points = self.mapGrid.randomRectangle(pt, n, candidates)
            if len(points) == n:
                break
        self.setPositions(points, self.allies)
        outline = self.mapGrid.outlineGrid(points, candidates, length=2)
        vacant = vacant.difference(points).difference(outline)
        allyGrid = sorted(points + outline)

        # Pick PC points, starting with a cluster near the allies
        candidates = sorted(vacant)
        count = 0
        while True:
            allyPt = random.sample(allyGrid, 1)[0]
            d = random.randint(8, 16)
            pt = self.mapGrid.randomNearbyPoint(allyPt, d, candidates, dh=10, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(2, 5)
            points = set(self.mapGrid.randomRectangle(pt, n, candidates))
            if len(points) < 6:
                break
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        candidates = sorted(vacant)
        points2 = set()
        while len(points) + len(points2) < 11:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, 9)
            grid = self.mapGrid.randomRectangle(pt, n, candidates)
            points2.update(grid)
            if len(points) + len(points2) > 18:
                points2 = set()
        points.update(points2)
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points2, vacant, length=2)
        vacant = vacant.difference(points2).difference(outline)

        # Set boss cluster
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            grid = self.mapGrid.randomRectangle(pt, 5, candidates)
            if len(grid) > len(self.bossCluster):
                break
        self.setPositions(grid, self.bossCluster)
        vacant = vacant.difference(grid)

        # Build and set enemy clusters
        candidates = sorted(vacant)
        points = set()
        while len(points) < 4*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, 9)
            grid = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(grid)
        self.setPositions(points, self.enemiesAnywhere)
        vacant = vacant.difference(points)

        self.setPCDirections(self.allies)
        self.setEnemyDirections()

# Team up with Hyzantian (Booker et al) and fight Aesfrosti (Avlora et al)
class MS08B_X13(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms08b_x13_battle_01', 1)

        gdag3 = self.enemyPositions.pop()
        gdag1 = self.enemyPositions.pop()
        self.booker = self.enemyPositions.pop()
        self.allies = [
            gdag3, gdag1, self.booker,
        ]

        avlora = self.enemyPositions[0] # Boss AI -> Normal (Just make it Normal from the start)
        spr1 = self.enemyPositions[1]
        spr2 = self.enemyPositions[2]
        swd3 = self.enemyPositions[3]
        swd4 = self.enemyPositions[4]
        swd1 = self.enemyPositions[5]
        swd2 = self.enemyPositions[6]
        bow1 = self.enemyPositions[7]
        rod1 = self.enemyPositions[8]
        spr3 = self.enemyPositions[9]
        spr4 = self.enemyPositions[10]
        bow3 = self.enemyPositions[11]
        bow4 = self.enemyPositions[12]

        self.bossCluster = [
            avlora, swd3, swd4,
        ]

        self.nearBooker = [
            bow1,
        ]

        self.enemiesAnywhere = [
            spr1, spr2, swd1, swd2,
            rod1, spr3, spr4, bow3, bow4,
        ]

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 11))

        # Change AI -- don't bother with Avlora's first turn
        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[2].getArg(1) == 'UNIT_MASTER_CH_P016', funcs[2].getArg(1)
        funcs[2].setArg(2, 'Normal')

        # Puddles
        puddles = self.battleCommon.getLocalFunction('StartPuddle')
        points = set()
        candidates = sorted(vacant)
        while len(points) < len(puddles):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, 10)
            path = self.mapGrid.randomWalk(pt, n)
            points.update(path)
        for line in puddles:
            line.deleteLine()
        for x, y in points:
            newLine = line.copyLine()
            newLine.setArg(1, float(x))
            newLine.setArg(2, float(y))

        # Pick ally points
        candidates = sorted(vacant)
        n = len(self.allies)
        while True:
            pt = random.sample(candidates, 1)[0]
            points = self.mapGrid.randomRectangle(pt, n, candidates)
            if len(points) == n:
                break
        self.setPositions(points, self.allies)
        outline = self.mapGrid.outlineGrid(points, candidates, length=2)
        vacant = vacant.difference(points).difference(outline)
        allyGrid = sorted(points + outline)

        # Pick PC points, starting with a cluster near the allies
        candidates = sorted(vacant)
        count = 0
        while True:
            allyPt = random.sample(allyGrid, 1)[0]
            d = random.randint(8, 16)
            pt = self.mapGrid.randomNearbyPoint(allyPt, d, candidates, dh=10, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(2, 5)
            points = set(self.mapGrid.randomRectangle(pt, n, candidates))
            if len(points) < 6:
                break
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        candidates = sorted(vacant)
        points2 = set()
        while len(points) + len(points2) < 11:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, 9)
            grid = self.mapGrid.randomRectangle(pt, n, candidates)
            points2.update(grid)
            if len(points) + len(points2) > 18:
                points2 = set()
        points.update(points2)
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points2, vacant, length=2)
        vacant = vacant.difference(points2).difference(outline)

        # Set boss cluster
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            grid = self.mapGrid.randomRectangle(pt, 5, candidates)
            if len(grid) > len(self.bossCluster):
                break
        self.setPositions(grid, self.bossCluster)
        vacant = vacant.difference(grid)

        # Build and set enemy clusters
        candidates = sorted(vacant)
        points = set()
        while len(points) < 4*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, 9)
            grid = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(grid)
        self.setPositions(points, self.enemiesAnywhere)
        vacant = vacant.difference(points)

        # Set archer somewhat near booker
        booker = (self.booker.X, self.booker.Y)
        count = 0
        while True:
            d = random.randint(5, 10)
            point = self.mapGrid.randomNearbyPoint(booker, d, vacant, dh=10, tol=count//10)
            if point:
                break
            count += 1
        self.setPositions([point], self.nearBooker)

        self.setPCDirections()
        self.setEnemyDirections()


class MS09_X14(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms09_x14_battle_01', 0, 'ms09_x14_battle_S_01')

        travis = self.enemyPositions[0]
        trish = self.enemyPositions[1]
        dag1 = self.enemyPositions[2]
        dag2 = self.enemyPositions[3]
        bow1 = self.enemyPositions[4]
        bow2 = self.enemyPositions[5]
        bow3 = self.enemyPositions[6]
        clb1 = self.enemyPositions[7]
        clb2 = self.enemyPositions[8]
        bok1 = self.enemyPositions[9]
        bok2 = self.enemyPositions[10]
        rod1 = self.enemyPositions[11]
        rod2 = self.enemyPositions[12]

        self.boss3 = [
            trish, bow3,
        ]

        self.bow1 = [
            bow1, bok1,
        ]

        self.bow2 = [
            bow2, bok2,
        ]

        self.enemiesAnywhere = [
            travis, dag1, dag2,
            clb1, clb2, rod1, rod2,
        ]

        self.aiBoss3Mov = 73
        self.aiBow1Mov = 74
        self.aiBow2Mov = 75
        self.aiBow3Mov = 76
        self.aiBow4Mov = 77

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 0))

        aiSettings = self.battle.getLocalFunction('ChangeAISettings')
        assert aiSettings[0][1].getArg(1) == 'UNIT_MASTER_CH_P015', aiSettings[0][1].getArg(1)
        aiSettings[0][1].setArg(2, 'AISetting_Boss3')
        line = aiSettings[0][-1]
        dag1 = line.copyLine()
        dag1.setArg(1, 'DAG1')
        dag1.setArg(2, 'AISetting_Dag2')
        dag2 = line.copyLine()
        dag2.setArg(1, 'DAG2')
        dag2.setArg(2, 'AISetting_Dag2')

        # Use as starting points for Trisha and bow/bok AIs
        highPoints = [
            (5, 14), (5, 9), (9, 7), (12, 11),
        ]

        enemyPts = set()

        # Set Trisha's AI first
        pt = random.sample(highPoints, 1)[0]
        boss3 = self.mapGrid.bfs(pt, 100, vacant)

        # Bow 1
        pt = random.sample(highPoints, 1)[0]
        bow1 = self.mapGrid.bfs(pt, 30, vacant)

        # Bow 2
        pt = random.sample(highPoints, 1)[0]
        bow2 = self.mapGrid.bfs(pt, 30, vacant)

        # Set starting tiles for these enemies
        candidates = sorted(vacant.intersection(boss3))
        pts = random.sample(candidates, len(self.boss3))
        self.setPositions(pts, self.boss3)
        vacant = vacant.difference(pts)
        enemyPts = enemyPts.union(pts)
        assert len(enemyPts) == len(self.boss3)

        candidates = sorted(vacant.intersection(bow1))
        pts = random.sample(candidates, len(self.bow1))
        self.setPositions(pts, self.bow1)
        vacant = vacant.difference(pts)
        enemyPts = enemyPts.union(pts)
        assert len(enemyPts) == len(self.boss3) + len(self.bow1)

        candidates = sorted(vacant.intersection(bow2))
        pts = random.sample(candidates, len(self.bow2))
        self.setPositions(pts, self.bow2)
        vacant = vacant.difference(pts)
        enemyPts = enemyPts.union(pts)
        assert len(enemyPts) == len(self.boss3) + len(self.bow1) + len(self.bow2)

        outline = self.mapGrid.outlineGrid(enemyPts, vacant, length=1)
        vacant = vacant.difference(outline)

        # Set these AI grids
        self.setAIMoveGrid(self.aiBoss3Mov, boss3)
        self.setAIMoveGrid(self.aiBow1Mov, bow1)
        self.setAIMoveGrid(self.aiBow3Mov, bow1)
        self.setAIMoveGrid(self.aiBow2Mov, bow2)
        self.setAIMoveGrid(self.aiBow4Mov, bow2)

        # Make sure PCs don't start right next to these enemies just because
        # It's okay of other enemies end up here, hence filtering late!
        vacant = vacant.difference(bow1)
        vacant = vacant.difference(bow2)

        # Set playable characters
        points = set()
        candidates = sorted(vacant)
        while len(points) < 12:
            n = random.randint(2, 10)
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)
        self.setPlayerPositions(points)

        # Do rest of enemies - purely random sample
        candidates = sorted(vacant)
        pts = random.sample(candidates, len(self.enemiesAnywhere))
        self.setPositions(pts, self.enemiesAnywhere)
        vacant = vacant.difference(pts)

        self.setPCDirections()
        self.setEnemyDirections()

class MS09_X15(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms09_x15_battle_01', 0, 'ms09_x15_battle_S_01')

        self.booker = self.enemyPositions[0] # Wait -> Boss
        rod1 = self.enemyPositions[1]
        bow1 = self.enemyPositions[2] # Bow
        bow2 = self.enemyPositions[3] # Bow
        swd2 = self.enemyPositions[4] # Swd
        swd3 = self.enemyPositions[5]
        swd4 = self.enemyPositions[6]
        dag1 = self.enemyPositions[7] # Dag
        dag2 = self.enemyPositions[8] # Dag2
        dag3 = self.enemyPositions[9] # Dag
        bow3 = self.enemyPositions[10] # Bow
        bow4 = self.enemyPositions[11] # Bow
        sld1 = self.enemyPositions[12]
        sld2 = self.enemyPositions[13]

        self.bossCluster = [
            self.booker, rod1,
        ]

        self.enemiesAnywhere = [
            bow1, bow2, swd2, swd3, swd4, dag1,
            dag2, dag3, bow3, bow4, sld1, sld2,
        ]

        # NOTES AI
        # - change bow2 grid to be the same as bow
        # - make sure the boss' "Wait" grid/tile is the same point as where he starts
        # - also make sure that point is contained within the boss grid
        self.aiBow1Mov = 48
        self.aiBow2Mov = 49
        self.aiWaitMov = 57
        self.aiBossMov = 47

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 11))

        # Set bow 2 grid
        grid = self.getAIMoveGrid(self.aiBow1Mov)
        self.setAIMoveGrid(self.aiBow2Mov, grid)

        # Set PC grids
        points = set()
        candidates = sorted(vacant)
        pcPoint = self.mapGrid.randomEdgePoint()
        count = 0
        while len(points) < 12:
            d = random.randint(0, 4)
            pt = self.mapGrid.randomNearbyPoint(pcPoint, d, candidates, dh=30, tol=count//10)
            count += 1
            if pt:
                n = random.randint(2, 10)
                rect = self.mapGrid.randomRectangle(pt, n, candidates)
                points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, candidates, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Set boss cluster
        bookerPoint = self.mapGrid.greatestDistance(pcPoint, tol=2)
        grid = self.mapGrid.bfs(bookerPoint, 90, candidates)
        points = set([bookerPoint])
        candidates = sorted(vacant)
        while len(points) < len(self.bossCluster):
            n = random.randint(2, 5)
            pt = self.mapGrid.randomNearbyPoint(bookerPoint, n, candidates)
            if pt:
                points.add(pt)
        self.setPositions(points, self.bossCluster)
        vacant = vacant.difference(grid).difference(points)

        # Set wait grid
        self.setAIMoveGrid(self.aiWaitMov, [(self.booker.X, self.booker.Y)])
        self.setAIMoveGrid(self.aiBossMov, grid)

        # Set enemy positions
        candidates = sorted(vacant)
        points = random.sample(candidates, len(self.enemiesAnywhere))
        self.setPositions(points, self.enemiesAnywhere)
        vacant = vacant.difference(points)

        self.setPCDirections()
        self.setEnemyDirections()

class MS10A_X16(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms10a_x16_battle_01', 1, 'ms10a_x16_battle_S_01')

        self.svarog = self.enemyPositions.pop(0) # Ally: aisetting7 -> AISetting3 -> AISetting4
        self.sycras = self.enemyPositions[0] # AISetting5 -> AISetting4 (defeat count or PC lands on "BoosGo" tile)
        sld1 = self.enemyPositions[1]
        sld2 = self.enemyPositions[2]
        bow1 = self.enemyPositions[3] # AISetting6 -> AISetting4
        bok1 = self.enemyPositions[4]
        sld3 = self.enemyPositions[5]
        sld4 = self.enemyPositions[6]
        swd1 = self.enemyPositions[7]
        swd2 = self.enemyPositions[8]
        bow2 = self.enemyPositions[9]
        bow3 = self.enemyPositions[10]
        bok2 = self.enemyPositions[11]
        assert len(self.enemyPositions) == 12

        self.enemiesRemaining = [
            sld1, sld2, bow1, bok1, sld3, sld4,
            swd1, swd2, bow2, bow3, bok2,
        ]

        self.aiSetting5 = 35
        

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Set initial Svarog's AI -- can move anywhere
        # Bow1, 2, 3 can move anywhere
        aiSettings = self.battle.getLocalFunction('ChangeAISettings')
        funcs = aiSettings[0]
        assert funcs[0].getArg(1) == 'UNIT_MASTER_CH_N104'
        funcs[0].setArg(2, 'AISetting4')
        for i in range(2, 5):
            assert funcs[i].getArg(1)[:3] == 'BOW'
            funcs[i].setArg(2, 'AISetting4')

        # Delete Svarog's AI changes
        funcs = self.battle.getLocalFunction('AddEventTrigger')
        assert funcs[5].getArg(1) == 'LINE2GO'
        funcs[5].deleteLine()
        assert funcs[6].getArg(1) == 'LINE3GO'
        funcs[6].deleteLine()

        # Pick spot for Sycras
        candidates = sorted(vacant)
        sycrasPoint = random.sample(candidates, 1)[0]
        self.sycras.X, self.sycras.Y = sycrasPoint        
        self.setAIMoveGrid(self.aiSetting5, [sycrasPoint])
        vacant.remove(sycrasPoint)
        outline = self.mapGrid.outlineGrid([sycrasPoint], vacant, length=2)
        vacant = vacant.difference(outline)

        # Update 'BoosGo' tile specs.
        # PC lands on tile and Sycras can now move anywhere
        boosgo = self.mapGrid.outlineGrid([sycrasPoint], vacant, length=8)
        self.mapGrid.clearSpecs('BoosGo')
        self.mapGrid.addSpec('BoosGo', boosgo)

        # Get point and grid for Svarog
        candidates = sorted(vacant.difference(boosgo))
        random.shuffle(candidates)
        minPath0 = 18
        maxPath0 = 24
        for svarogPoint in candidates:
            minPath = minPath0
            maxPath = maxPath0
            path = self.mapGrid.shortestPath(svarogPoint, sycrasPoint)
            # Make sure Svarog does not start in boosgo
            while minPath < len(path):
                if path[minPath] in boosgo:
                    minPath += 1
                    maxPath += 1
                else:
                    break
            # Check if path is too short
            if len(path) < minPath:
                continue
            # Shorten path if needed
            if len(path) > maxPath:
                n = random.randint(minPath, maxPath)
                svarogPoint = path[n]
            if svarogPoint in vacant:
                break
        self.svarog.X, self.svarog.Y = svarogPoint
        vacant.remove(svarogPoint)
        outline = self.mapGrid.outlineGrid([svarogPoint], vacant, length=2)
        vacant = vacant.difference(outline)

        # Spawn enemies within boosgo
        lines = []
        while len(lines) < 2:
            x, y = random.sample(boosgo, 1)[0]
            p0 = (x, y)
            if random.random() < 0.5:
                p1 = (x+1, y)
                p2 = (x-1, y)
            else:
                p1 = (x, y+1)
                p2 = (x, y-1)
            if p1 in vacant and self.mapGrid.isValid(*p1):
                if p2 in vacant and self.mapGrid.isValid(*p2):
                    lines.append([p2, p0, p1])
                    vacant = vacant.difference(lines[-1])
        genFuncs = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        for i, (line, func) in enumerate(zip(lines, genFuncs)):
            self.setWaki(func, line[1])
            spec = f"ZOUEN0{i}"
            self.mapGrid.clearSpecs(spec)
            self.mapGrid.addSpec(spec, line)

        # Place PCs near Svarog
        candidates = sorted(vacant.difference(boosgo))
        length = 6
        while True:
            startPoints = self.mapGrid.outlineGrid([svarogPoint], candidates, length)
            if startPoints:
                break
            length += 1
        pcPoints = set()
        count = 0
        dh = 5
        while len(pcPoints) < 13:
            d = random.randint(2, 4)
            sp = random.sample(startPoints, 1)[0]
            pt = self.mapGrid.randomNearbyPoint(sp, d, candidates, dh=dh + count//20, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(4, 10)
            grid = self.mapGrid.randomRectangle(pt, n, candidates)
            pcPoints.update(grid)
            if len(pcPoints) > 20:
                pcPoints = set()
        self.setPlayerPositions(pcPoints)
        outline = self.mapGrid.outlineGrid(pcPoints, vacant, length=2)
        vacant = vacant.difference(pcPoints).difference(startPoints).difference(outline)

        # Place enemies near PCs
        length = 4
        while True:
            startPoints = self.mapGrid.outlineGrid(pcPoints, vacant, length)
            if len(startPoints) > len(self.enemiesRemaining):
                break
            length += 1
        candidates = sorted(vacant)
        points = set()
        count = 0
        while len(points) < 3*len(self.enemiesRemaining):
            refPt = random.sample(startPoints, 1)[0]
            d = random.randint(5, 10)
            pt = self.mapGrid.randomNearbyPoint(refPt, d, candidates, dh=10, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(4, 10)
            grid = self.mapGrid.randomRectangle(pt, n, candidates, d=10)
            points.update(grid)
        self.setPositions(points, self.enemiesRemaining)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(startPoints).difference(outline)

        self.setPCDirections(allies=self.svarog)
        self.setEnemyDirections()

class MS10A_X17(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms10a_x17_battle_01', 1)

        UNIT_MASTER_CH_N007 = self.enemyPositions[0]
        spr1 = self.enemyPositions[1]
        spr2 = self.enemyPositions[2]
        spr3 = self.enemyPositions[3]
        spr4 = self.enemyPositions[4]
        rod1 = self.enemyPositions[5]
        rod2 = self.enemyPositions[6]
        assert len(self.enemyPositions) == 7

        self.aiSetting1 = 15
        self.aiSetting3 = 17

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Let AI Setting 3 be the full grid
        grid = self.getAIMoveGrid(self.aiSetting1)
        self.setAIMoveGrid(self.aiSetting3, grid)

        # Start all enemies on the goal grid
        points = set()
        grid = sorted(vacant)
        while len(points) < len(self.enemyPositions):
            pt = random.sample(grid, 1)[0]
            n = random.randint(1, len(self.enemyPositions))
            rect = self.mapGrid.randomRectangle(pt, n, grid)
            points.update(rect)
        self.setPositions(points, self.enemyPositions)
        vacant = vacant.difference(points)

        # Ensure pcs aren't too close to enemies
        nmPts = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPts, vacant, length=1)
        vacant = vacant.difference(outline)

        # Set points for PCs
        points = set()
        candidates = sorted(vacant)
        while len(points) < len(self.pcPositions):
            pt = random.sample(grid, 1)[0]
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        points = random.sample(sorted(points), len(self.pcPositions))
        self.setPlayerPositions(points)
        vacant = vacant.difference(points)

        self.setPCDirections()
        self.setEnemyDirections()

class MS10B_X18(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms10b_x18_battle_01', 1, 'ms10b_x18_battle_S_01')

        UNIT_MASTER_CH_M101 = self.enemyPositions[0]
        bow1 = self.enemyPositions[1]
        bow2 = self.enemyPositions[2]
        dag1 = self.enemyPositions[3]
        dag2 = self.enemyPositions[4]
        bow3 = self.enemyPositions[5]
        bow4 = self.enemyPositions[6]
        dag4 = self.enemyPositions[7]
        dag5 = self.enemyPositions[8]
        bow5 = self.enemyPositions[9]
        dag3 = self.enemyPositions[10]
        rod1 = self.enemyPositions[11]
        assert len(self.enemyPositions) == 12

        self.stopEnemy = [ # Start at short distance from (7, 7)
            dag2, 
        ]

        self.enemiesAnywhere = [
            UNIT_MASTER_CH_M101, bow1, bow2, dag1,
            bow3, bow4, dag4, dag5, bow5, dag3, rod1,
        ]

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Pick points for PCs -- Note that Serenoa and Benedict have fixed points (cannot be moved)
        # They are intended to have these fixed points separate from the party.
        # TODO: Find a better way to update the initial table to allow for stuff like this.
        candidates = sorted(vacant)
        pt = random.sample(candidates, 1)[0]
        reqPCs = set([pt])
        count = 0
        while True:
            pt2 = self.mapGrid.randomNearbyPoint(pt, 1, candidates, tol=count//10)
            count += 1
            if pt2:
                break
        reqPCs.add(pt2)
        outline = self.mapGrid.outlineGrid(reqPCs, candidates, length=3)
        vacant = vacant.difference(reqPCs).difference(outline)
        
        points = set(reqPCs)
        candidates = sorted(vacant)
        while len(points) < 10:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, 8)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 16:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, candidates, length=2)
        vacant = vacant.difference(points).difference(outline)
        self.setUnitTable(reqPCs)

        # Put dag2 somewhere near (7, 7)
        assert len(self.stopEnemy) == 1
        candidates = sorted(vacant)
        count = 0
        while True:
            d = random.randint(2, 10)
            pt = self.mapGrid.randomNearbyPoint((7, 7), d, candidates, tol=count//10)
            if pt:
                break
            count += 1
        self.setPositions([pt], self.stopEnemy)
        vacant.remove(pt)        
        
        # Build and set enemy clusters
        candidates = sorted(vacant)
        points = set()
        while len(points) < 3*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, 9)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesAnywhere)
        vacant = vacant.difference(points)

        self.setPCDirections()
        self.setEnemyDirections()

class MS10B_X19(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms10b_x19_battle_01', 1)

        sorsley = self.enemyPositions[0]
        sld1 = self.enemyPositions[1]
        sld2 = self.enemyPositions[2]
        bok1 = self.enemyPositions[3]
        bok2 = self.enemyPositions[4]
        dag1 = self.enemyPositions[5]
        dag2 = self.enemyPositions[6]
        assert len(self.enemyPositions) == 7

        # Note: These grids are the same for all enemies.
        # Use it just to pick where enemies start.
        self.aiSLDMov = 22

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Start all enemies on the goal grid
        points = set()
        grid = sorted(vacant)
        while len(points) < len(self.enemyPositions):
            pt = random.sample(grid, 1)[0]
            n = random.randint(1, len(self.enemyPositions))
            rect = self.mapGrid.randomRectangle(pt, n, grid)
            points.update(rect)
        self.setPositions(points, self.enemyPositions)
        vacant = vacant.difference(points)

        # Ensure pcs aren't too close to enemies
        nmPts = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPts, vacant, length=1)
        vacant = vacant.difference(outline)

        # Set points for PCs
        points = set()
        candidates = sorted(vacant)
        while len(points) < len(self.pcPositions):
            pt = random.sample(grid, 1)[0]
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        points = random.sample(sorted(points), len(self.pcPositions))
        self.setPlayerPositions(points)
        vacant = vacant.difference(points)

        self.setPCDirections()
        self.setEnemyDirections()

class MS11_X20(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms11_x20_battle_01', 1, 'ms11_x20_battle_S_01')

        self.rufus = self.enemyPositions[0] # AISetting2
        self.jerrom = self.enemyPositions[1] # BOSS tile for AI -> Right_Wing (turn 2) -> Normal
        bow1 = self.enemyPositions[2] # Left_Archer
        bow2 = self.enemyPositions[3] # Roof
        bow3 = self.enemyPositions[4] # Left
        bow4 = self.enemyPositions[5] # Right
        bow5 = self.enemyPositions[6] # Roof
        bow6 = self.enemyPositions[7] # Left
        spr1 = self.enemyPositions[8] # Roof
        spr2 = self.enemyPositions[9] # NONE
        spr3 = self.enemyPositions[10] # Right_Wing
        spr4 = self.enemyPositions[11] # Left_Wing
        spr5 = self.enemyPositions[12] # NONE
        rod1 = self.enemyPositions[13] # Roof
        rod2 = self.enemyPositions[14] # Roof
        rod3 = self.enemyPositions[15] # Right
        assert len(self.enemyPositions) == 16

        # Allies
        self.enemyPositions.pop(0)

        # Enemies
        self.bows = { # LEFT_ARCHER or RIGHT_ARCHER
            'BOW1': bow1,
            'BOW2': bow2,
            'BOW3': bow3,
            'BOW4': bow4,
            'BOW5': bow5,
            'BOW6': bow6,
        }

        self.rods = { # ROOF
            'ROD1': rod1,
            'ROD2': rod2,
            'ROD3': rod3,
        }

        self.sprs = { # Left_Wing or Right_Wing
            'SPR1': spr1,
            'SPR3': spr3,
            'SPR4': spr4,
        }

        self.enemiesAnywhere = [ # NONE for AI, or AISetting2
            spr2, spr5,
        ]

        # Do Jerrom separately sampling from Right_Wing

        self.aiLeftArcher = 40
        self.aiRightArcher = 39
        self.aiLeftWing = 38
        self.aiRightWing = 37
        self.aiRoof = 35
        self.aiBoss = 41
        self.aiSetting2 = 36

        changeAISettings = self.battle.getLocalFunction('ChangeAISettings')
        self.changeAISettings = {}
        for setting in changeAISettings:
            n = setting.getArg(1)
            self.changeAISettings[n] = setting

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Start with PCs to prevent overlapping with enemies
        points = set()
        candidates = sorted(vacant)
        while len(points) < 13:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points, ally=self.rufus)
        outline = self.mapGrid.outlineGrid(points, candidates, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Next do LEFT/RIGHT_ARCHER
        gridLeft = sorted(vacant.intersection(self.getAIMoveGrid(self.aiLeftArcher)))
        gridLeft += self.mapGrid.outlineGrid(gridLeft, vacant)
        gridRight = sorted(vacant.intersection(self.getAIMoveGrid(self.aiRightArcher)))
        gridRight += self.mapGrid.outlineGrid(gridRight, vacant)
        while True:
            nL = []
            nR = []
            for key, enemy in self.bows.items():
                if random.random() < 1./2:
                    nL.append((key, enemy))
                else:
                    nR.append((key, enemy))
            # Make sure there's enough space
            if len(nL) <= len(gridLeft) and len(nR) <= len(gridRight):
                pointsLeft = random.sample(gridLeft, len(nL))
                pointsRight = random.sample(gridRight, len(nR))
                if set(pointsLeft).isdisjoint(pointsRight):
                    break
        vacant = vacant.difference(pointsLeft).difference(pointsRight)

        for i, (key, enemy) in enumerate(nL):
            enemy.X, enemy.Y = pointsLeft[i]
            if random.random() < 0.5:
                self.changeAISettings[key].setArg(2, 'LEFT_ARCHER')
            else:
                self.changeAISettings[key].setArg(2, 'ROOF')
        for i, (key, enemy) in enumerate(nR):
            enemy.X, enemy.Y = pointsRight[i]
            if random.random() < 0.5:
                self.changeAISettings[key].setArg(2, 'RIGHT_ARCHER')
            else:
                self.changeAISettings[key].setArg(2, 'ROOF')

        # Next do Left/Right_Wing
        gridLeft = sorted(vacant.intersection(self.getAIMoveGrid(self.aiLeftWing)))
        gridLeft += self.mapGrid.outlineGrid(gridLeft, vacant)
        gridRight = sorted(vacant.intersection(self.getAIMoveGrid(self.aiRightWing)))
        gridRight += self.mapGrid.outlineGrid(gridRight, vacant)
        while True:
            nL = []
            nR = []
            for key, enemy in self.sprs.items():
                if random.random() < 1./2:
                    nL.append((key, enemy))
                else:
                    nR.append((key, enemy))
            if len(nL) <= len(gridLeft) and len(nR) <= len(gridRight):
                pointsLeft = random.sample(gridLeft, len(nL))
                pointsRight = random.sample(gridRight, len(nR))
                if set(pointsLeft).isdisjoint(pointsRight):
                    break
        vacant = vacant.difference(pointsLeft).difference(pointsRight)

        for i, (key, enemy) in enumerate(nL):
            enemy.X, enemy.Y = pointsLeft[i]
            if random.random() < 0.5:
                self.changeAISettings[key].setArg(2, 'Left_Wing')
            else:
                self.changeAISettings[key].setArg(2, 'ROOF')
        for i, (key, enemy) in enumerate(nR):
            enemy.X, enemy.Y = pointsRight[i]
            if random.random() < 0.5:
                self.changeAISettings[key].setArg(2, 'Right_Wing')
            else:
                self.changeAISettings[key].setArg(2, 'ROOF')

        # Next do healers/ROD
        gridLeft = sorted(vacant.intersection(self.getAIMoveGrid(self.aiLeftArcher)))
        gridLeft += self.mapGrid.outlineGrid(gridLeft, vacant)
        gridRight = sorted(vacant.intersection(self.getAIMoveGrid(self.aiRightArcher)))
        gridRight += self.mapGrid.outlineGrid(gridRight, vacant)
        while True:
            nL = []
            nR = []
            for key, enemy in self.rods.items():
                r = random.random()
                if r < 1./2:
                    nL.append((key, enemy))
                else:
                    nR.append((key, enemy))
            if len(nL) <= len(gridLeft) and len(nR) <= len(gridRight):
                pointsLeft = random.sample(gridLeft, len(nL))
                pointsRight = random.sample(gridRight, len(nR))
                if set(pointsLeft).isdisjoint(pointsRight):
                    break
        vacant = vacant.difference(pointsLeft).difference(pointsRight)

        for i, (key, enemy) in enumerate(nL):
            enemy.X, enemy.Y = pointsLeft[i]
            if random.random() < 0.5:
                self.changeAISettings[key].setArg(2, 'LEFT_ARCHER')
            else:
                self.changeAISettings[key].setArg(2, 'ROOF')
        for i, (key, enemy) in enumerate(nR):
            enemy.X, enemy.Y = pointsRight[i]
            if random.random() < 0.5:
                self.changeAISettings[key].setArg(2, 'RIGHT_ARCHER')
            else:
                self.changeAISettings[key].setArg(2, 'ROOF')

        # Place Jerrom in the Right_Wing
        gridRight = sorted(vacant.intersection(self.getAIMoveGrid(self.aiRightWing)))
        gridRight += self.mapGrid.outlineGrid(gridRight, vacant)
        pt = random.sample(gridRight, 1)[0]
        self.jerrom.X, self.jerrom.Y = pt
        self.setAIMoveGrid(self.aiBoss, [pt])
        vacant.remove(pt)
        
        # Build and set remaining enemies
        candidates = sorted(vacant)
        points = set()
        while len(points) < len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, 9)
            grid = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(grid)
        self.setPositions(points, self.enemiesAnywhere)
        vacant = vacant.difference(points)

        self.setPCDirections(allies=self.rufus)
        self.setEnemyDirections()

class MS11_X21(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms11_x21_battle_01', 1, 'ms11_x21_battle_S_01')

        self.jerrom = self.enemyPositions.pop(0) # AISetting2
        silvio = self.enemyPositions[0] # AISetting1
        sld1 = self.enemyPositions[1] # AIAssassin
        sld2 = self.enemyPositions[2] # AIAssassin
        bow1 = self.enemyPositions[3] # AISetting1
        rod1 = self.enemyPositions[4] # AISetting1
        bok1 = self.enemyPositions[5] # AISetting1
        bok2 = self.enemyPositions[6] # AISetting1
        rufus = self.enemyPositions[7]
        sld3 = self.enemyPositions[8] # AIAssassin
        sld4 = self.enemyPositions[9] # AIAssassin
        bok3 = self.enemyPositions[10]
        bow4 = self.enemyPositions[11]
        assert len(self.enemyPositions) == 12

        # The rest of the enemies
        self.enemiesSetting1 = [
            bow1, rod1, bok1, bok2, silvio,
        ]

        self.enemiesRemaining = [
            sld1, sld2, sld3, sld4, bok3,
            bow4, rufus,
        ]

        self.aiSetting5 = 26
        self.aiSetting4 = 25
        self.aiSetting1 = 23

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # First set spawn point
        while True:
            pt = self.mapGrid.randomEdgePoint()
            grid = self.mapGrid.randomWalk(pt, 4)
            if pt and len(grid) == 4:
                break
        func = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')[0]
        self.setWaki(func, pt)
        self.mapGrid.clearSpecs('ZOUEN01')
        self.mapGrid.addSpec('ZOUEN01', grid)

        # Set PCs
        points = set()
        candidates = sorted(vacant)
        while len(points) < 12:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points, ally=self.jerrom)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Set enemies on AISetting1
        grid = sorted(vacant.intersection(self.getAIMoveGrid(self.aiSetting1)))
        grid += self.mapGrid.outlineGrid(grid, vacant)
        points = set()
        n = len(self.enemiesSetting1)
        while len(points) < 3*n:
            pt = random.sample(grid, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, n, grid)
            points.update(rect)
        self.setPositions(points, self.enemiesSetting1)
        vacant = vacant.difference(points)
        
        # Set the rest of the enemies
        grid = sorted(vacant)
        points = set()
        n = len(self.enemiesRemaining)
        while len(points) < 3*n:
            pt = random.sample(grid, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, n, grid)
            points.update(rect)
        self.setPositions(points, self.enemiesRemaining)
        vacant = vacant.difference(points)

        self.setPCDirections(allies=self.jerrom)
        self.setEnemyDirections()

class MS12_X22(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms12_x22_battle_01', 1, 'ms12_x22_battle_S_01')

        self.jerrom = self.enemyPositions[0]
        silvio = self.enemyPositions[1]
        sld1 = self.enemyPositions[2] # AISetting1 -> AISetting2
        bow1 = self.enemyPositions[3] # AISetting3 -> AISetting2
        swd1 = self.enemyPositions[4]
        spr1 = self.enemyPositions[5]
        rod1 = self.enemyPositions[6] # AISetting1 -> AISetting2
        swd2 = self.enemyPositions[7]
        bok1 = self.enemyPositions[8] # AISetting3 -> AISetting2
        rufus = self.enemyPositions[9]
        bow2 = self.enemyPositions[10] # AISetting3 -> AISetting2
        sld2 = self.enemyPositions[11] # AISetting3 -> AISetting2
        bow3 = self.enemyPositions[12] # AISetting1 -> AISetting2
        bok2 = self.enemyPositions[13] # AISetting1 -> AISetting2
        swd3 = self.enemyPositions[14]
        assert len(self.enemyPositions) == 15
        self.enemyPositions.pop(0)

        self.enemiesAISetting = {
            'SLD1': sld1,
            'BOW1': bow1,
            'ROD1': rod1,
            'BOK1': bok1,
            'BOW2': bow2,
            'SLD2': sld2,
            'BOW3': bow3,
            'BOK2': bok2,
        }

        self.enemiesAnywhere = [
            silvio, swd1, spr1, swd2, rufus, swd3, 
        ]

        self.aiSetting1 = 19
        self.aiSetting2 = 20
        self.aiSetting3 = 21
        self.aiSetting4 = 22 # UNUSED

        changeAISettings = self.battle.getLocalFunction('ChangeAISettings')[0]
        self.changeAISettings = {}
        for setting in changeAISettings:
            n = setting.getArg(1)
            self.changeAISettings[n] = setting
        del self.changeAISettings['SLD4']
        assert len(self.changeAISettings) == len(self.enemiesAISetting)

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Set PCs
        points = set()
        candidates = sorted(vacant)
        while len(points) < len(self.pcPositions) + 1:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        points = random.sample(sorted(points), 12)
        self.setPlayerPositions(points, ally=self.jerrom)
        outline = self.mapGrid.outlineGrid(points, candidates, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Enemies in setting 1 or 3
        grid1 = sorted(vacant.intersection(self.getAIMoveGrid(self.aiSetting1)))
        grid1 += self.mapGrid.outlineGrid(grid1, vacant)
        grid3 = sorted(vacant.intersection(self.getAIMoveGrid(self.aiSetting3)))
        grid3 += self.mapGrid.outlineGrid(grid3, vacant)
        while True:
            n1 = []
            n3 = []
            for key, enemy in self.enemiesAISetting.items():
                if random.random() < 1./2:
                    n1.append((key, enemy))
                else:
                    n3.append((key, enemy))
            # Make sure there's enough space
            if len(n1) <= len(grid1) and len(n3) <= len(grid3):
                points1 = random.sample(grid1, len(n1))
                points3 = random.sample(grid3, len(n3))
                if set(points1).isdisjoint(points3):
                    break
        vacant = vacant.difference(points1).difference(points3)

        for i, (key, enemy) in enumerate(n1):
            self.changeAISettings[key].setArg(2, 'AISetting1')
            enemy.X, enemy.Y = points1[i]
        for i, (key, enemy) in enumerate(n3):
            self.changeAISettings[key].setArg(2, 'AISetting3')
            enemy.X, enemy.Y = points3[i]

        # Set remaining enemies
        points = set()
        candidates = sorted(vacant)
        while len(points) < 2*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, len(self.enemiesAnywhere))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        vacant = vacant.difference(points)
        self.setPositions(points, self.enemiesAnywhere)

        self.setPCDirections(allies=self.jerrom)
        self.setEnemyDirections()

class MS13_X24(Level):
    def __init__(self, pak):
        self.pak = pak
        super().__init__(pak, 'ms13_x24_battle_01', 0, 'ms13_x24_battle_S')

        self.gimmickLubs = [
            Lub(pak, "ms13_x24_research_01_before.lub"),
            Lub(pak, "ms13_x24_research_01_after.lub"),
            Lub(pak, "ms13_x24_battle_01_before.lub"),
            Lub(pak, "ms13_x24_battle_01_after.lub"),
            Lub(pak, "ms13_x24_research_01_change_map.lub"),
        ]

        gimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        self.barricadeGimmicks = gimmicks[:4]
        self.barricades = [ENEMYPOSITION(i, self.mapGrid) for i in self.barricadeGimmicks]
        self.grapeGimmicks = gimmicks[4:]
        self.grapes = [ENEMYPOSITION(i, self.mapGrid) for i in self.grapeGimmicks]

        sycras = self.enemyPositions[0] # Gate
        spr1 = self.enemyPositions[1] # AI_Search1
        bow1 = self.enemyPositions[2] # AI_Search2
        bow2 = self.enemyPositions[3] # AI_Search3
        swd1 = self.enemyPositions[4] # AI_Search3
        bok1 = self.enemyPositions[5] # Gate
        rod2 = self.enemyPositions[6] # Gate
        swd2 = self.enemyPositions[7] # AI_Search5
        bow3 = self.enemyPositions[8] # Tower
        assert len(self.enemyPositions) == 9

        self.archer = [bow3]
        self.gridGroup = {
            'Search1': [spr1],
            'Search2': [bow1],
            'Search3': [bow2, swd1],
            'Search4': [sycras, bok1, rod2],
            'Search5': [swd2],
        }

        self.aiMovGroup = {
            'Search1': 69,
            'Search2': 77,
            'Search3': 78,
            'Search4': 79,
            'Search5': 74,
        }
        
        self.aiAtkGroup = {
            'Search1': 53,
            'Search2': 61,
            'Search3': 62,
            'Search4': 63,
            'Search5': 58,
        }
        
        self.towerMov = 80
        self.towerAtk = 64
        self.area11Mov = 84
        self.area51Mov = 73
        self.area52Mov = 76


    def update(self):
        super().update()
        if self.isRandomized:
            for lub in self.gimmickLubs:
                lub.update()

    def random(self):
        self.isRandomized = True
        vacant = set(filter(lambda pt: pt[0] < 34, self.mapGrid.getAccessible(0, 0)))
        goalCandidates = set(vacant)
        vacant = vacant.difference([
            (8, 20), (8, 19), (8, 18),   # Near PC start / enemy 1
            (2, 4), (2, 3), (2, 2),      # Near enemy 2
            (11, 3), (11, 2), (11, 1),   # Near enemy 2 / 3
            (14, 14), (14, 13), (14, 12) # Near enemy 3 / 4 / 5
        ])

        # Set AI grids
        aiGrids = {k: self.mapGrid.getIdxs(k) for k in self.gridGroup}
        randomMap = {k:k for k in aiGrids}
        keys = list(randomMap.keys())
        for i, k in enumerate(randomMap.keys()):
            r = random.sample(keys[i:], 1)[0]
            randomMap[k], randomMap[r] = randomMap[r], randomMap[k]

        for k, r in randomMap.items():
            self.mapGrid.clearSpecs(k)
            self.mapGrid.addSpec(k, aiGrids[r])
            vacant = vacant.difference(aiGrids[r])

        # Place Outside Search
        def outside(grid):
            outline = set()
            for x,y in grid:
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    pt = (x+dx, y+dy)
                    if not self.mapGrid.isValid(*pt):
                        continue
                    if pt in grid:
                        continue
                    outline.add(pt)
            return sorted(outline)
            
        for k, r in randomMap.items():
            if k == 'Search4': continue
            n = f"Outide_{k}"
            grid = outside(aiGrids[r])
            self.mapGrid.clearSpecs(n)
            self.mapGrid.addSpec(k, grid)
            vacant = vacant.difference(grid)

        # Place enemies
        def makeCand(i, j):
            x = []
            for a, b in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                x.append((a+i, b+j))
            return x
        points = {
            'Search1': makeCand(7, 14),
            'Search2': makeCand(6, 6),
            'Search3': makeCand(15, 8),
            'Search4': makeCand(23, 14),
            'Search5': makeCand(15, 18),
        }
        for k, r in randomMap.items():
            # Place enemies
            n = len(self.gridGroup[k])
            pts = random.sample(points[r], n)
            self.setPositions(pts, self.gridGroup[k])
            # AI
            self.setAIMoveGrid(self.aiMovGroup[k], pts)
            self.setAIAtkGrid(self.aiAtkGroup[k], pts)
            # Dark grids
            if k == 'Search4': continue
            if k == 'Search5': continue
            for a, (x, y) in enumerate(pts):
                g = []
                assert self.mapGrid.isValid(x, y)
                for i in range(-1, 2):
                    for j in range(-1, 2):
                        if self.mapGrid.isValid(x+i, y+j):
                            g.append((x+i, y+j))

                if k == 'Search1':
                    q = f"{k}_1"
                elif k == 'Search2':
                    q = k
                elif k == 'Search3':
                    q = f"{k}_{a+1}"
                else:
                    sys.exit()

                s = f"Dark_{q}"
                self.mapGrid.clearSpecs(s)
                self.mapGrid.addSpec(s, g)

                s = f"D_Outside_{q}"
                og = self.mapGrid.outlineGrid(g, vacant, length=1)
                self.mapGrid.clearSpecs(s)
                self.mapGrid.addSpec(s, og)

        # Archer
        tower1 = [(8,18), (8,19), (8,20)]
        tower2 = [(2, 2), (2, 3), (2, 4)]
        tower3 = [(11, 1), (11, 2), (11, 3)]
        tower4 = [(14, 12), (14, 13), (14, 14)]
        tower5 = self.getAIMoveGrid(self.towerMov)
        if randomMap['Search4'] == 'Search1':
            archerGridCand = [tower1, tower4]
        elif randomMap['Search4'] == 'Search2':
            archerGridCand = [tower2, tower3]
        elif randomMap['Search4'] == 'Search3':
            archerGridCand = [tower3, tower4]
        elif randomMap['Search4'] == 'Search4':
            archerGridCand = [tower5]
        elif randomMap['Search4'] == 'Search5':
            archerGridCand = [tower1, tower4]
        else:
            sys.exit()

        archerGrid = random.sample(archerGridCand, 1)[0]
        self.setAIMoveGrid(self.towerMov, archerGrid)
        self.setAIAtkGrid(self.towerAtk, archerGrid)
        self.setPositions(archerGrid, self.archer)

        # Goal & GoalFront
        candidates = sorted(goalCandidates)
        if randomMap['Search4'] == 'Search1':
            goalGrid = self.mapGrid.bfs((2, 19), 50, candidates)
        elif randomMap['Search4'] == 'Search2':
            goalGrid = self.mapGrid.bfs((1, 1), 50, candidates)
        elif randomMap['Search4'] == 'Search3':
            goalGrid = self.mapGrid.bfs((15, 2), 50, candidates)
        elif randomMap['Search4'] == 'Search4':
            pt = random.sample([(30, 15), (22, 20)], 1)[0]
            goalGrid = self.mapGrid.bfs(pt, 50, candidates)
        elif randomMap['Search4'] == 'Search5':
            goalGrid = self.mapGrid.bfs((12, 20), 50, candidates)
        else:
            sys.exit()
        grid = aiGrids[randomMap['Search4']] + goalGrid
        goalFront = self.mapGrid.outlineGrid(grid, vacant, length=2)
        self.mapGrid.clearSpecs('GoalFront')
        self.mapGrid.addSpec('GoalFront', goalFront)
        self.mapGrid.clearSpecs('Goal')
        self.mapGrid.addSpec('Goal', goalGrid)

        # Set camera for Goal
        funcs = self.battle.getLocalFunction('ChangeStageCameraToMapGrid')
        pt = self.mapGrid.clusterMean(goalGrid)
        funcs[0].setArg(1, float(pt[0]))
        funcs[0].setArg(2, float(pt[1]))
        funcs[1].setArg(1, float(pt[0]))
        funcs[1].setArg(2, float(pt[1]))
        
        # Barricades of Search4
        grid = aiGrids[randomMap['Search4']] + goalGrid
        edges = self.mapGrid.edgesOfGrid(grid)
        n = random.randint(len(edges)//2, len(edges)-1)
        pts = random.sample(edges, n)
        self.setGimmickPositions(pts, self.barricadeGimmicks, self.barricades)
        vacant = vacant.difference(pts)

        # Ensure pcs aren't too close to enemies
        nmPts = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPts, vacant, length=1)
        vacant = vacant.difference(outline)

        # Set PCs
        candidates = sorted(vacant)
        pt_g = self.mapGrid.clusterMean(goalGrid)
        pt_ref = self.mapGrid.greatestDistance(pt_g, grid=candidates, tol=5)
        pcPoints = set()
        tol = 0
        count = 0
        while len(pcPoints) < 13:
            n = random.randint(2, 6)
            d = random.randint(0, 5)
            pt = self.mapGrid.randomNearbyPoint(pt_ref, d, candidates, dh=30, tol=tol)
            count += 1
            if count % 50 == 0:
                tol += 1
            if pt is None:
                continue
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            pcPoints.update(rect)
            if len(pcPoints) > 20:
                pcPoints = set()
        self.setPlayerPositions(pcPoints)
        vacant = vacant.difference(pcPoints)

        # AI after trigger
        area11 = self.mapGrid.getValid()
        area51 = goalGrid + goalFront
        area52 = goalGrid
        self.setAIMoveGrid(self.area11Mov, area11)
        self.setAIMoveGrid(self.area51Mov, area51)
        self.setAIMoveGrid(self.area52Mov, area52)

        # Grapes
        candidates = sorted(vacant)
        grapePoints = set()
        while len(grapePoints) < 30:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(4, 10)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            grapePoints.update(rect)
        vacant = vacant.difference(grapePoints)
        self.setGimmickPositions(grapePoints, self.grapeGimmicks, self.grapes)

        # Waki
        def wakiCluster(n):
            candidates = sorted(vacant)
            tol = 0
            count = 0
            while True:
                pt = random.sample(goalFront, 1)[0]
                d = random.randint(0, 25)
                cluster = self.mapGrid.nearbyCluster(pt, d, n, candidates, tol=tol)
                if cluster and len(cluster) == n:
                    break
                count += 1
                if count % 50 == 0:
                    tol += 1
            return cluster

        wakiPoints = set()

        cluster = wakiCluster(3)
        wakiPoints.update(cluster)
        vacant = vacant.difference(cluster)
        
        cluster = wakiCluster(2)
        wakiPoints.update(cluster)
        vacant = vacant.difference(cluster)
        
        cluster = wakiCluster(1)
        wakiPoints.update(cluster)
        vacant = vacant.difference(cluster)

        funcs = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        wakiPoints = sorted(wakiPoints)
        for f, p in zip(funcs, wakiPoints):
            self.setWaki(f, p)

        self.setPCDirections()
        self.setEnemyDirections()

class MS13_X25(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms13_x25_battle_01', 1, 'ms13_x25_battle_S_01')

        thalas = self.enemyPositions[0] # AI_TARA0 -> AI_GORYU -> AI_SHIP
        bow1 = self.enemyPositions[1] # AI_GORYU
        bow2 = self.enemyPositions[2] # AI_SHIP
        bow3 = self.enemyPositions[3] # AI_SHIP
        bow4 = self.enemyPositions[4] # AI_CENTER
        sld1 = self.enemyPositions[5] # AI_BRIDGE  --> CHANGE TO AI_LEFT_GRID
        sld2 = self.enemyPositions[6] # AI_LEFT_GRID
        sld3 = self.enemyPositions[7] # AI_LEFT_GRID
        rod1 = self.enemyPositions[8] # AI_SHIP
        rod2 = self.enemyPositions[9] # AI_BRIDGE_HELP
        rid1 = self.enemyPositions[10] # AI_BIRD -> AI_ALL -> AI_SHIP
        rid2 = self.enemyPositions[11] # AI_BIRD -> AI_ALL -> AI_SHIP
        assert len(self.enemyPositions) == 12


        self.boss = [
            thalas, bow1, rod1,
        ]

        # self.support = [ # AI_BRIDGE_HELP -- consider changing to AI_SHIP
        #     rod2,
        # ]

        self.enemShip = [ # AI_SHIP -- make these points above height of 5???????
            bow2, bow3, #rod1,
            rod2,
        ]

        self.enemBird = [
            rid1, rid2,
        ]

        self.enemLeft = [ # include in AI_CENTER, AI_LEFT, ...., with spawned reinforcements!
            sld2, sld3, bow4,
            sld1,
        ]

        # EV_LOOK & BIRD_LOOK related ai settings
        # Also EnemyGen2 -- this group can be anywhere!
        self.aiAll = 72
        self.aiLeft = 76

        # EnemyGen1 -- should start somewhere around here
        self.aiCenterShip = 69
        self.aiCenterL = 70
        self.aiCenter = 67

        # The rest
        self.aiGoryu = 77
        self.aiBird = 73
        self.aiBridgeHelp = 75
        # self.aiTaigan = 74
        self.aiLeftGird = 78
        self.aiBridge = 71
        # self.aiMast = 64
        self.aiShip = 65
        self.aiRightBow = 66
        self.aiTarao = 68

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))
        self.setAIMoveGrid(self.aiAll, vacant)

        # Update initial AIs
        funcs = self.battle.getLocalFunction('ChangeAISettings')
        assert funcs[0][1].getArg(1) == 'SLD1'
        funcs[0][3].setArg(2, 'AI_LEFT_GIRD')
        assert funcs[0][2].getArg(1) == 'ROD1'
        funcs[0][3].setArg(2, 'AI_GORYU')
        assert funcs[0][3].getArg(1) == 'ROD2'
        funcs[0][3].setArg(2, 'AI_SHIP')
        assert funcs[0][7].getArg(1) == 'UNIT_MASTER_CH_N103'
        funcs[0][7].setArg(2, 'AI_GORYU')

        # PC positions at the edge
        # Place containers nearby
        # Set EV_LOOK and BIRD_LOOK nearby
        edgePt = self.mapGrid.randomEdgePoint(grid=vacant)
        candidates = sorted(vacant)
        edgeGrid = self.mapGrid.randomRectangle(edgePt, 6, candidates)
        # Containers
        containers = self.battleCommon.getLocalFunction('CreateGimmickData')
        outline = self.mapGrid.outlineGrid(edgeGrid, vacant, length=1)
        allEdges = self.mapGrid.edgesOfGrid()
        # Pick a target point for testing
        if (0, 0) not in edgeGrid and (0,0) not in outline:
            target = (0, 0)
        else:
            target = (26, 0)
        candidates = set(vacant)
        containerTiles = set()
        keepEmpty = []
        refPt = random.sample(edgeGrid, 1)[0]
        random.shuffle(outline)
        containerTiles = []
        for pt in outline:
            containerTiles.append(pt)
            path = self.mapGrid.shortestPath(refPt, target, grid=candidates, block=containerTiles)
            if path is None:
                containerTiles.remove(pt)
                continue
        containerPositions = [ENEMYPOSITION(c, self.mapGrid) for c in containers]
        self.setGimmickPositions(containerTiles, containers, containerPositions)
        vacant = vacant.difference(edgeGrid)
        vacant = vacant.difference(outline) # Make sure to filter out the whole outline
        
        # EV_LOOK grid
        length = 2
        while True:
            evLookGrid = self.mapGrid.outlineGrid(edgeGrid, vacant, length=length)
            if len(evLookGrid) > 60:
                break
            length += 1
        self.mapGrid.clearSpecs('EV_LOOK')
        self.mapGrid.addSpec('EV_LOOK', evLookGrid)
        # BIRD_LOOK grid
        candidates = vacant.difference(evLookGrid).difference(edgeGrid)
        length = 1
        while True:
            points = self.mapGrid.outlineGrid(edgeGrid+evLookGrid, candidates, length)
            if points:
                break
            length += 1
        while True:
            pt = random.sample(points, 1)[0]
            birdLookGrid = self.mapGrid.randomRectangle(pt, 60, candidates)
            if len(birdLookGrid) > 60:
                break
        self.mapGrid.clearSpecs('BIRD_LOOK')
        self.mapGrid.addSpec('BIRD_LOOK', birdLookGrid)

        # Reinforcements -- near bird and ev for AI purposes
        candidates = sorted(vacant.difference(evLookGrid).difference(birdLookGrid))
        outline = self.mapGrid.outlineGrid(birdLookGrid + evLookGrid, candidates)
        pt1 = random.sample(outline, 1)[0]
        tol = 0
        count = 0
        while True:
            d = random.randint(1, 20)
            pt_reinf = self.mapGrid.randomNearbyPoint(pt1, d, vacant, dh=10, tol=tol)
            count += 1
            if count % 50 == 0:
                tol += 1
            if pt_reinf is None:
                continue
            reinfGrid1 = self.mapGrid.randomWalk(pt_reinf, 3, d=10)
            if len(reinfGrid1) == 3:
                break
        pt2 = random.sample(outline, 1)[0]
        tol = 0
        count = 0
        while True:
            d = random.randint(1, 20)
            pt_reinf = self.mapGrid.randomNearbyPoint(pt2, d, vacant, dh=10, tol=tol)
            count += 1
            if count % 50 == 0:
                tol += 1
            if pt_reinf is None:
                continue
            reinfGrid2 = self.mapGrid.randomWalk(pt_reinf, 3, d=10)
            if set(reinfGrid2).intersection(reinfGrid1):
                continue
            if len(reinfGrid2) == 3:
                break
        self.mapGrid.clearSpecs('Reinforce')
        self.mapGrid.addSpec('Reinforce', reinfGrid1 + reinfGrid2)

        pt = self.mapGrid.clusterMean(reinfGrid1)
        func = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')[0]
        self.setWaki(func, pt)

        pt = self.mapGrid.clusterMean(reinfGrid2)
        func = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')[1]
        self.setWaki(func, pt)

        # Reinforcement AI
        # Make all the same as evlook and bird
        # Maybe consider tweaking these in the future?
        grid = birdLookGrid + evLookGrid + outline
        self.setAIMoveGrid(self.aiCenterShip, grid)
        self.setAIMoveGrid(self.aiCenterL, grid)
        self.setAIMoveGrid(self.aiCenter, grid)

        # Add the rest of the PCs
        candidates = sorted(vacant)
        points = set(edgeGrid)
        nPos = len(self.pcPositions) + 1 # +1 for MILO
        while len(points) < nPos:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, nPos)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > nPos + 6:
                points = set(edgeGrid)
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, candidates, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Left enemies
        grid = self.mapGrid.outlineGrid(birdLookGrid + evLookGrid, vacant, length=2)
        grid += birdLookGrid + evLookGrid
        candidates = sorted(vacant.intersection(grid))
        pts = random.sample(candidates, len(self.enemLeft))
        self.setPositions(pts, self.enemLeft)
        vacant = vacant.difference(pts)
        self.setAIMoveGrid(self.aiLeftGird, grid)
        self.setAIMoveGrid(self.aiLeft, grid)

        # Remaining enemies and AI settings
        edges = self.mapGrid.heightDiffTiles()
        edges = list(filter(lambda x: x in vacant, edges))
        while True:
            grid = set(vacant)

            # Generate grids
            enemShipGrid = set()
            candidates = sorted(grid)
            while len(enemShipGrid) < 90:
                pt = random.sample(candidates, 1)[0]
                enemShipGrid.update(self.mapGrid.bfs(pt, 90, grid))

            enemBossGrid = set()
            candidates = sorted(grid)
            while len(enemBossGrid) < 20:
                pt = random.sample(candidates, 1)[0]
                enemBossGrid.update(self.mapGrid.bfs(pt, 20, grid))

            enemBirdGrid = set() # Any point to these? Add enemies to ship grid????
            while len(enemBirdGrid) < 10:
                pt = random.sample(edges, 1)[0]
                enemBirdGrid.update(self.mapGrid.bfs(pt, 10, grid))

            enemShipGrid = sorted(enemShipGrid)
            enemBossGrid = sorted(enemBossGrid)
            enemBirdGrid = sorted(enemBirdGrid)

            # Pick enemy points
            outline = self.mapGrid.outlineGrid(enemBossGrid, grid, length=4)
            candidates = sorted(grid.intersection(enemBossGrid+outline))
            if len(grid) < len(self.boss):
                continue
            while True:
                bossPts = self.mapGrid.randomCluster(10, candidates)
                if len(bossPts) >= len(self.boss):
                    break
            grid = grid.difference(bossPts)

            outline = self.mapGrid.outlineGrid(enemBirdGrid, grid, length=4)
            candidates = sorted(grid.intersection(enemBirdGrid+outline))
            if len(grid) < len(self.enemBird):
                continue
            birdPts = random.sample(candidates, len(self.enemBird))
            grid = grid.difference(birdPts)

            outline = self.mapGrid.outlineGrid(enemShipGrid, grid, length=4)
            candidates = sorted(grid.intersection(enemShipGrid+outline))
            if len(grid) < len(self.enemShip):
                continue
            shipPts = random.sample(candidates, len(self.enemShip))
            grid = grid.difference(shipPts)

            # Set enemies at points
            self.setPositions(bossPts, self.boss)
            self.setPositions(birdPts, self.enemBird)
            self.setPositions(shipPts, self.enemShip)

            # Set grids for AI
            self.setAIMoveGrid(self.aiGoryu, enemBossGrid)
            self.setAIMoveGrid(self.aiBird, enemBirdGrid)
            self.setAIMoveGrid(self.aiShip, enemShipGrid)

            break

        self.setPCDirections()
        self.setEnemyDirections()


class MS13_X26(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms13_x26_battle_01', 1, 'ms13_x26_battle_S_01')

        erika = self.enemyPositions[0]
        sld1 = self.enemyPositions[1]
        sld2 = self.enemyPositions[2]
        sld3 = self.enemyPositions[3]
        rod1 = self.enemyPositions[4]
        rod2 = self.enemyPositions[5]
        spr1 = self.enemyPositions[6]
        spr2 = self.enemyPositions[7]
        thalas = self.enemyPositions[8]
        bow1 = self.enemyPositions[9]
        bow2 = self.enemyPositions[10]
        bow3 = self.enemyPositions[11]
        bok1 = self.enemyPositions[12]
        bok2 = self.enemyPositions[13]
        swd1 = self.enemyPositions[14]
        assert len(self.enemyPositions) == 15

        self.boss1 = erika
        self.boss2 = thalas

        self.mobsAiIdx = {
            sld1: 2,
            sld2: 3,
            sld3: 4,
            rod1: 5,
            rod2: 6,
            spr1: 7,
            bow1: 8,
            bow2: 9,
            bow3: 10,
            bok1: 11,
            bok2: 12,
            swd1: 13,
            spr2: None,
        }

        self.aiMob1 = 40
        self.aiMob2 = 41
        self.aiBoss1 = 36
        self.aiBoss2 = 37


    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 13, dh=30))

        # Setup AI grids
        grid = list(filter(lambda pt: pt[0] < 16, vacant))
        self.setAIMoveGrid(self.aiBoss1, grid)
        self.setAIMoveGrid(self.aiBoss2, grid)

        mob1Grid = self.getAIMoveGrid(self.aiMob1)
        mob2Grid = self.getAIMoveGrid(self.aiMob2)
        mob1Grid += list(filter(lambda pt: pt[1] < 13, grid))
        mob2Grid += list(filter(lambda pt: pt[1] > 13, grid))
        mob1Grid = list(set(mob1Grid))
        mob2Grid = list(set(mob2Grid))
        self.setAIMoveGrid(self.aiMob1, mob1Grid)
        self.setAIMoveGrid(self.aiMob2, mob2Grid)

        # Group mobs 1 and 2
        func = self.battle.getLocalFunction('ChangeAISettings')[0]
        def setAI(i, m):
            if not i: return
            f = func[i]
            f.setArg(2, m)

        mob1 = []
        mob2 = []
        for k, v in self.mobsAiIdx.items():
            if random.random() < 0.5:
                mob1.append(k)
                setAI(v, 'AISetting_Mob1')
            else:
                mob2.append(k)
                setAI(v, 'AISetting_Mob2')

        if random.random() < 0.5:
            mob1.append(self.boss1)
        else:
            mob2.append(self.boss1)

        if random.random() < 0.5:
            mob1.append(self.boss2)
        else:
            mob2.append(self.boss2)

        # Place PCs
        candidates = sorted(vacant)
        points = set()
        while len(points) < 16:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(4, 18)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 32:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Place mobs1
        candidates = vacant.intersection(mob1Grid)
        length = 1
        while len(candidates) < 3*len(mob1):
            outline = self.mapGrid.outlineGrid(mob1Grid, vacant, length)
            candidates.update(outline)
            length += 1
        candidates = sorted(candidates)
        points = set()
        while len(points) < 3*len(mob1):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(len(mob1)//2, len(mob1))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, mob1)
        vacant = vacant.difference(points)

        # Place mobs2
        candidates = vacant.intersection(mob2Grid)
        length = 1
        while len(candidates) < 3*len(mob2):
            outline = self.mapGrid.outlineGrid(mob2Grid, vacant, length)
            candidates.update(outline)
            length += 1
        candidates = sorted(candidates)
        points = set()
        while len(points) < 3*len(mob2):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(len(mob2)//2, len(mob2))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, mob2)
        vacant = vacant.difference(points)

        self.setPCDirections()
        self.setEnemyDirections()


class MS14_X27(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms14_x27_battle_01', 1, 'ms14_x27_battle_S_01')

        self.gimmicksLub = [
            Lub(pak, "ms14_x27_battle_01_before.lub"),
            Lub(pak, "ms14_x27_battle_01_after.lub"),
        ]

        self.gimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        self.barricades = [ENEMYPOSITION(i, self.mapGrid) for i in self.gimmicks]

        erika = self.enemyPositions[0]  # AISetting_Boss1 -> Boss3 -> ... -> ... -> Boss5
        thalas = self.enemyPositions[1] # AISetting_Boss2 -> Boss4 -> ... -> ... -> Boss6
        sld1 = self.enemyPositions[2] # AISetting_Sld1 -> ... -> Normal3 -> Support3
        sld2 = self.enemyPositions[3] # AISetting_Sld1 -> ... -> Normal3 -> Support3
        sld3 = self.enemyPositions[4] # AISetting_Sld2 -> ... -> Normal3 -> Support4
        sld4 = self.enemyPositions[5] # AISetting_Sld2 -> ... -> Normal3 -> Support4
        rod1 = self.enemyPositions[6] # AISetting_Support1 -> ... -> ... -> ...
        rod2 = self.enemyPositions[7] # AISetting_Support2 -> ... -> ... -> ...
        bok1 = self.enemyPositions[8] # AISetting_Support1 -> ... -> ... -> ...
        bok2 = self.enemyPositions[9] # AISetting_Support2 -> ... -> ... -> ...
        bow1 = self.enemyPositions[10] # AISetting_Swd1 -> ... -> Support1 -> ...
        bow2 = self.enemyPositions[11] # AISetting_Swd2 -> ... -> Support2 -> ...
        self.bow3 = self.enemyPositions[12] # AISetting_Bow1 -> ... -> ... -> Support1
        self.bow4 = self.enemyPositions[13] # AISetting_Bow2 -> ... -> ... -> Support2
        assert len(self.enemyPositions) == 14


        self.sld = [
            sld1, sld2,
        ]

        self.archers = [
            self.bow3, self.bow4,
        ]

        self.enemiesAnywhere = [
            erika, thalas,
            sld3, sld4,
            rod1, rod2,
            bok1, bok2,
            bow1, bow2,
        ]

        # bow3 and bow4: randomly assign to points in aiBow1 and aiBow2???
        # Nah, just skip
        self.bow3.wontMove()
        self.bow4.wontMove()

        self.aiBoss1 = 83 # Erika's starting point
        self.aiBoss2 = 84 # Thalas' starting point
        self.aiBoss3 = 85
        self.aiBossAtk3 = 65
        self.aiBoss4 = 86
        self.aiBossAtk4 = 66
        self.aiBoss5 = 93
        self.aiBoss6 = 94

        self.aiNormal3 = 95

        self.aiSupport1 = 98
        self.aiSupport2 = 99
        self.aiSupport3 = 89
        self.aiSupport4 = 90

        self.aiBow1 = 87 # add (35, 19)
        self.aiBow2 = 88 # add (35, 8)

        self.aiSld1 = 91
        self.aiSld2 = 92

        self.aiSwd1 = 100
        self.aiSwdAtk1 = 80
        self.aiSwd2 = 101
        self.aiSwdAtk2 = 81

    def update(self):
        super().update()
        if self.isRandomized:
            for lub in self.gimmicksLub:
                lub.update()

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(40, 15, dh=30))
        omit = [(41, 18), (41, 19), (41, 10), (41, 9), (34, 17), (35, 17), (34, 10), (35, 10)]
        vacant = vacant.difference(omit) # Remove points at ladders

        # Archers that won't move
        vacant.remove((self.bow3.X, self.bow3.Y))
        vacant.remove((self.bow4.X, self.bow4.Y))

        # Change boss ai
        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[0].getArg(2) == 'AISetting_Boss1'
        funcs[0].setArg(2, 'AISetting_Boss3')
        assert funcs[1].getArg(2) == 'AISetting_Boss2'
        funcs[1].setArg(2, 'AISetting_Boss4')

        # Setup AI grids
        grid = list(filter(lambda pt: pt[0] > 34, vacant))
        self.setAIMoveGrid(self.aiBoss3, grid)
        self.setAIAtkGrid(self.aiBossAtk3, grid)
        self.setAIMoveGrid(self.aiBoss4, grid)
        self.setAIAtkGrid(self.aiBossAtk4, grid)
        self.setAIMoveGrid(self.aiBoss5, grid)
        self.setAIMoveGrid(self.aiBoss6, grid)
        self.setAIMoveGrid(self.aiNormal3, grid)
        self.setAIMoveGrid(self.aiSupport1, grid)
        self.setAIMoveGrid(self.aiSupport2, grid)
        self.setAIMoveGrid(self.aiSupport3, grid)
        self.setAIMoveGrid(self.aiSupport4, grid)

        bow1Grid = self.getAIMoveGrid(self.aiBow1)
        bow1Grid.append((35, 19))
        self.setAIMoveGrid(self.aiBow1, bow1Grid)
        bow2Grid = self.getAIMoveGrid(self.aiBow2)
        bow2Grid.append((35, 8))
        self.setAIMoveGrid(self.aiBow2, bow2Grid)

        # Pick enemy grid of size ~50 tiles
        candidates = sorted(vacant)
        # candidates = list(filter(lambda pt: self.mapGrid.isHeight(*pt, 21, tol=1), candidates))
        enemyGrid = set()
        while True:
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, 40, candidates, d=20)
            enemyGrid.update(rect)
            if len(enemyGrid) > 60:
                enemyGrid = set()
            if len(enemyGrid) > 40:
                break
        enemyGrid = sorted(enemyGrid)
        outline = self.mapGrid.outlineGrid(enemyGrid, candidates)
        self.setAIMoveGrid(self.aiSwd1, enemyGrid + outline)
        self.setAIMoveGrid(self.aiSwd2, enemyGrid + outline)
        self.setAIAtkGrid(self.aiSwdAtk1, enemyGrid + outline)
        self.setAIAtkGrid(self.aiSwdAtk2, enemyGrid + outline)

        # Set barricades
        candidates = enemyGrid
        candidates = list(filter(lambda pt: self.mapGrid.isHeight(*pt, 21, tol=1), candidates))
        while len(candidates) < 40:
            candidates += self.mapGrid.outlineGrid(candidates, vacant)
        barracks = set()
        while len(barracks) <  15:
            line = sorted(self.mapGrid.flatLine(candidates))
            n = random.randint(3, 6)
            if len(line) < n+3:
                barracks.update(line)
            else:
                idx = random.randint(0, len(line)-n)
                barracks.update(line[idx:idx+n])
            if len(barracks) > 18:
                barracks = set()
        sldGrid = random.sample(sorted(barracks), 4)
        barracks = barracks.difference(sldGrid)
        self.setGimmickPositions(barracks, self.gimmicks, self.barricades)
        vacant = vacant.difference(barracks).difference(sldGrid)
        enemyGrid = set(enemyGrid).intersection(vacant)

        ## Set soldiers near their grids
        pts = random.sample(sldGrid, 2)
        sldCand = pts + self.mapGrid.outlineGrid(pts, vacant, length=1)
        points = random.sample(sldCand, 2)
        self.setPositions(points, self.sld)
        enemyGrid = enemyGrid.difference(points)
        self.setAIMoveGrid(self.aiSld1, sldGrid)
        self.setAIMoveGrid(self.aiSld2, sldGrid)

        ## Place the rest of the enemies in the enemy grid
        assert len(enemyGrid) > len(self.enemiesAnywhere), enemyGrid
        self.setPositions(enemyGrid, self.enemiesAnywhere)

        # Updates for PCs
        # Enemy outline
        enemyPoints = [(e.X, e.Y) for e in self.enemyPositions]
        enemyOutline = self.mapGrid.outlineGrid(enemyPoints, vacant, length=1)
        vacant = vacant.difference(enemyOutline).difference(enemyPoints)
        # Barrack outline
        barrackOutline = self.mapGrid.outlineGrid(barracks, vacant, length=1)
        if len(vacant) - len(barrackOutline) > 20:
            vacant = vacant.difference(barrackOutline)
        # Other grids
        vacant = vacant.difference(enemyGrid).difference(bow1Grid).difference(bow2Grid).difference(sldGrid)

        # Pick PC positions
        candidates = sorted(vacant)
        points = set()
        while len(points) < 16:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(3, 14)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 22:
                points = set()
        self.setPlayerPositions(points)

        self.setPCDirections()
        self.setEnemyDirections()

class MS14_X28(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms14_x28_battle_01', 1, 'ms14_x28_battle_S_01')

        self.gimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        self.barricades = [ENEMYPOSITION(i, self.mapGrid) for i in self.gimmicks]
        self.gimmickAI = self.battle.getLocalFunction('SetMapGimmickUnitCampForAI') # Need to update names

        avlora   = self.enemyPositions[0] # AISetting_Boss1 -> AISetting_Boss2 -> AISetting_Boss3 -> AISetting_Normal
        mob_sld1 = self.enemyPositions[1] # AISetting_Right2 -> AISetting_Normal -> AISetting_Support1
        mob_sld2 = self.enemyPositions[2] # AISetting_Left2 -> AISetting_Normal -> AISetting_Support1
        mob_swd1 = self.enemyPositions[3] # AISetting_Normal -> AISetting_Normal -> AISetting_Support1
        mob_swd2 = self.enemyPositions[4] # AISetting_Right -> AISetting_Normal -> AISetting_Support1
        mob_swd3 = self.enemyPositions[5] # AISetting_Left -> AISetting_Normal -> AISetting_Support1
        mob_swd4 = self.enemyPositions[6] # AISetting_Normal -> AISetting_Normal -> AISetting_Support1
        mob_rod1 = self.enemyPositions[7] # AISetting_Right -> AISetting_Normal -> AISetting_Support1
        mob_rod2 = self.enemyPositions[8] # AISetting_Left -> AISetting_Normal -> AISetting_Support1
        mob_bok1 = self.enemyPositions[9] # AISetting_Right -> AISetting_Normal -> AISetting_Support1
        mob_bok2 = self.enemyPositions[10] # AISetting_Left -> AISetting_Normal -> AISetting_Support1
        mob_bow1 = self.enemyPositions[11] # AISetting_Right -> AISetting_Normal -> AISetting_Support1
        mob_bow4 = self.enemyPositions[12] # AISetting_Left -> AISetting_Normal -> AISetting_Support1
        assert len(self.enemyPositions) == 13

        self.boss = [
            avlora
        ]

        self.left = [
            mob_sld2, mob_swd3, mob_rod2, mob_bok2, mob_bow4
        ]

        self.right = [
            mob_sld1, mob_swd2, mob_rod1, mob_bok1, mob_bow1
        ]

        self.normal = [ # Randomly pick placing these with right or left mobs
            mob_swd1, mob_swd4,
        ]

        self.aiBoss1 = 93
        self.aiBoss2 = 94
        self.aiBoss3 = 103
        self.aiRight = 99
        self.aiLeft  = 98
        self.aiRight2 = 101
        self.aiLeft2  = 107
        self.aiSupport1 = 112
        self.aiNormal = 108


    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 20))

        # Set boss3 and support1 to be anywhere
        self.setAIMoveGrid(self.aiBoss3, vacant)
        self.setAIMoveGrid(self.aiSupport1, vacant)

        # Group enemies together
        leftEnem = list(self.left)
        rightEnem = list(self.right)
        normalEnem = list(self.normal)
        while normalEnem:
            if random.random() < 0.5:
                rightEnem.append(normalEnem.pop())
            else:
                leftEnem.append(normalEnem.pop())
        if random.random() < 0.5:
            rightEnem += self.boss
        else:
            leftEnem += self.boss

        # Set normal to large subset of the map
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            normalGrid = self.mapGrid.randomRectangle(pt, 14*14, candidates)
            if 12*12 <= len(normalGrid) <= 256:
                break
        edgesGrid = self.mapGrid.outlineGrid(normalGrid, vacant)
        # normalGrid += edgesGrid

        # Set boss2 to be a subset of normal
        while True:
            pt = random.sample(normalGrid, 1)[0]
            boss2Grid = self.mapGrid.randomRectangle(pt, 80, normalGrid)
            if 60 <= len(boss2Grid) <= 130:
                break

        # Set boss1 to be a subset of boss2
        # NB: boss1 is just a single point in boss2 in vanilla
        while True:
            pt = random.sample(boss2Grid, 1)[0]
            boss1Grid = self.mapGrid.randomRectangle(pt, 20, boss2Grid)
            if 1 <= len(boss1Grid) <= 40:
                break

        # Start avlora outside of boss2

        # Left & right = normal + chunk outside of normal
        # pick point outside normal: maybe outline with length of 5
        #     then pick point from outline
        #     then do shortest path from point to normal,
        #     then outline shortest path
        # make sure chunks are sufficiently large (e.g. double or triple size of enemy list)
        # remove these chunks from candidates/vacant to ensure left/right don't overlap
        while True:
            candidates = sorted(vacant.difference(normalGrid))
            edgeCand = list(edgesGrid)

            ptL = random.sample(edgeCand, 1)[0]
            gridL = self.mapGrid.randomRectangle(ptL, 4*len(leftEnem), candidates)
            edgeCand = sorted(set(edgeCand).difference(gridL))
            candidates = sorted(set(candidates).difference(gridL))

            ptR = random.sample(edgeCand, 1)[0]
            gridR = self.mapGrid.randomRectangle(ptL, 4*len(rightEnem), candidates)
            
            if len(gridL) < 4*len(leftEnem):
                continue
            if len(gridR) < 4*len(rightEnem):
                continue

            break

        # Set ai grids
        self.setAIMoveGrid(self.aiBoss1, boss1Grid)
        self.setAIMoveGrid(self.aiBoss2, boss2Grid)
        self.setAIMoveGrid(self.aiNormal, normalGrid + edgesGrid)
        self.setAIMoveGrid(self.aiLeft, normalGrid + edgesGrid + gridL)
        self.setAIMoveGrid(self.aiLeft2, normalGrid + edgesGrid + gridL)
        self.setAIMoveGrid(self.aiRight, normalGrid + edgesGrid + gridR)
        self.setAIMoveGrid(self.aiRight2, normalGrid + edgesGrid + gridR)

        # Reinforcements
        self.mapGrid.clearSpecs('EventID_Reinforcement')
        self.mapGrid.clearSpecs('Reinforce')

        while True:
            candidates = self.mapGrid.outlineGrid(gridL, vacant, length=4)
            candidates += self.mapGrid.outlineGrid(gridR, vacant, length=4)
            candidates = set(candidates)
            
            reinforceGrid = list(self.mapGrid.flatLine(candidates, length=3))
            candidates = candidates.difference(reinforceGrid)
            reinforceGrid += list(self.mapGrid.flatLine(candidates, length=3))
            candidates = candidates.difference(reinforceGrid)
            reinforceGrid += list(self.mapGrid.flatLine(candidates, length=3))

            if len(reinforceGrid) == 9:
                break
        
        funcs = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        self.setWaki(funcs[0], reinforceGrid[4])
        self.setWaki(funcs[1], reinforceGrid[7])
        self.setWaki(funcs[2], reinforceGrid[1])
        self.setWaki(funcs[3], reinforceGrid[4])
        self.setWaki(funcs[4], reinforceGrid[7])

        eventID = vacant.difference(boss1Grid).difference(boss2Grid).difference(normalGrid).difference(gridL).difference(gridR)
        self.mapGrid.addSpec('EventID_Reinforcement', eventID)
        self.mapGrid.addSpec('Reinforce', reinforceGrid)

        # Enemy positions
        ptsLeft = random.sample(gridL, len(leftEnem))
        ptsRight = random.sample(gridR, len(rightEnem))
        self.setPositions(ptsLeft, leftEnem)
        self.setPositions(ptsRight, rightEnem)
        vacant = vacant.difference(ptsLeft).difference(ptsRight)
        outlineLeft = self.mapGrid.outlineGrid(ptsLeft, vacant, length=1)
        outlineRight = self.mapGrid.outlineGrid(ptsRight, vacant, length=1)
        vacant = vacant.difference(outlineLeft).difference(outlineRight)

        # Set barricades
        barricadePoints = set()
        while len(barricadePoints) < len(self.gimmicks):
            line = self.mapGrid.flatLine(vacant)
            barricadePoints.update(line)
        self.setGimmickPositions(barricadePoints, self.gimmicks, self.barricades)
        self.copyArgs(self.gimmicks, self.gimmickAI, 1)
        vacant = vacant.difference(barricadePoints)

        # Set PCs in Normal
        pts = set()
        candidates = sorted(vacant.intersection(normalGrid))
        while len(pts) < 17:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, 15)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            pts.update(rect)
            if len(pts) > 25:
                pts = set()
        self.setPlayerPositions(pts)
        vacant = vacant.difference(pts)

        self.setPCDirections()
        self.setEnemyDirections()

# No clue what to do for this level.
class MS14_X29(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms14_x29_battle_01', 1, 'ms14_x29_battle_S_01')

        # AI seems to change to setting 7 when PCs are on board, then 3 when not
        avlora = self.enemyPositions[0] # AISetting5 -> AISetting3
        sld1 = self.enemyPositions[1] # AISetting5 -> AISetting3
        self.bow1 = self.enemyPositions[2] # AISetting1
        bow2 = self.enemyPositions[3] # AISetting3
        self.bow4 = self.enemyPositions[4] # AISetting1
        sld2 = self.enemyPositions[5] # AISetting5 -> AISetting3
        rod2 = self.enemyPositions[6] # AISetting6
        rid1 = self.enemyPositions[7] # AISetting2
        rid2 = self.enemyPositions[8] # AISetting2
        rid3 = self.enemyPositions[9] # AISetting2
        assert len(self.enemyPositions) == 10

        self.bow1.wontMove()
        self.bow4.wontMove()

        self.boss = [
            avlora, rod2
        ]

        self.enemies = [ # Keep bow1 and bow4 in vanilla spots
            sld1, bow2, sld2, rid1, rid2, rid3,
        ]
        

    # Keep enemy AI as is.
    # It will encourage enemies on the PC boat to flee.
    # Kind of fun to chase Avlora!
    def random(self):
        self.isRandomized = True
        bows = [(self.bow1.X, self.bow1.Y), (self.bow4.X, self.bow4.Y)]
        enemBoat = set(filter(lambda p: p[1] < 15, self.mapGrid.getValid()))
        enemBoat = enemBoat.difference([(24, 9), (24, 10), (24, 11)])
        outline = self.mapGrid.outlineGrid(bows, enemBoat, length=1)
        enemBoat = enemBoat.difference(outline)
        pcBoat   = set(filter(lambda p: p[1] > 15, self.mapGrid.getValid()))
        
        # reinforcements
        if random.random() < 0.5:
            pt = random.sample(sorted(enemBoat), 1)[0]
        else:
            pt = random.sample(sorted(pcBoat), 1)[0]
        f = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')[0]
        self.setWaki(f, pt)

        # PCs
        n = random.randint(0, 8)
        m = 10 - n
        while True:
            points1 = set()
            while len(points1) < n:
                pt = random.sample(enemBoat, 1)[0]
                rect = self.mapGrid.randomRectangle(pt, n, enemBoat)
                points1.update(rect)
            points2 = set()
            while len(points2) < m:
                pt = random.sample(pcBoat, 1)[0]
                rect = self.mapGrid.randomRectangle(pt, m, pcBoat)
                points2.update(rect)
            points = points1.union(points2)
            if len(points) >= 12 and len(points) < 15:
                break
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, self.mapGrid.getValid(), length=1)
        enemBoat = enemBoat.difference(points).difference(outline)
        pcBoat = pcBoat.difference(points).difference(outline)

        # Enemies
        # Keep Avlora on the ship with fewer PC slots
        if len(points1) < len(points2):
            pts = random.sample(sorted(enemBoat), len(self.boss))
            self.setPositions(pts, self.boss)
            enemBoat = enemBoat.difference(pts)
        else:
            pts = random.sample(sorted(pcBoat), len(self.boss))
            self.setPositions(pts, self.boss)
            pcBoat = pcBoat.difference(pts)
        vacant = enemBoat.union(pcBoat)
        self.setPositions(vacant, self.enemies)
        
        self.setPCDirections()
        self.setEnemyDirections()

class MS15_X30(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms15_x30_battle_01', 1, 'ms15_x30_battle_S_01')

        self.symon = self.enemyPositions.pop(0) # AISetting4
        patriatte = self.enemyPositions[0] # AISetting5
        sld1 = self.enemyPositions[1] # AISetting2 -> AISetting3 (turn 50)
        spr1 = self.enemyPositions[2] # AISetting2 -> AISetting3
        sld2 = self.enemyPositions[3] # AISetting2 -> AISetting3
        swd1 = self.enemyPositions[4] # AISetting1 -> AISetting3 (turn 25)
        swd2 = self.enemyPositions[5] # AISetting1 -> AISetting3
        swd3 = self.enemyPositions[6] # AISetting1 -> AISetting3
        bow1 = self.enemyPositions[7]
        bow2 = self.enemyPositions[8]
        swd4 = self.enemyPositions[9]
        bok1 = self.enemyPositions[10]
        rod1 = self.enemyPositions[11]
        assert len(self.enemyPositions) == 12

        self.boss = [
            patriatte, rod1,
        ]

        self.swds = [ # AISetting1
            swd1, swd2, swd3,
        ]

        self.enemies = [ # 2-3 in or near AISetting4/5, rest anywhere
            spr1, sld1, sld2,
            bow1, bow2, swd4, bok1,
        ]

        self.aiSetting1 = 23
        self.aiSetting2 = 24
        self.aiSetting3 = 25
        self.aiSetting4 = 26 # AI 4 grid == 5 grid
        self.aiSetting5 = 27

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Set AISetting4/5 grids first
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            grid45 = self.mapGrid.randomRectangle(pt, 45, candidates)
            if len(grid45) >= 40:
                break
        self.setAIMoveGrid(self.aiSetting4, grid45)
        self.setAIMoveGrid(self.aiSetting5, grid45)

        # Use this grid to set boss and symon clusters
        pt1, pt2 = self.mapGrid.furthestPointsApart(grid45)

        candidates = sorted(vacant)
        n = random.randint(4, 8)
        allyGrid = self.mapGrid.bfs(pt1, n, candidates)
        allyGrid.remove(pt1)
        self.symon.X, self.symon.Y = pt1
        allyPoints = set(allyGrid)
        outline = self.mapGrid.outlineGrid(allyGrid, candidates)
        vacant = vacant.difference(allyGrid).difference(outline)

        candidates = sorted(vacant)
        n = random.randint(5, 10)
        enemyGrid = self.mapGrid.bfs(pt2, n, candidates)
        self.setPositions(enemyGrid, self.boss)
        outline = self.mapGrid.outlineGrid(enemyGrid, vacant, length=1)
        vacant = vacant.difference(enemyGrid).difference(outline)

        # Enemy grid -- AISetting1
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            grid1 = self.mapGrid.randomRectangle(pt, 100, candidates)
            if len(grid1) > 90:
                break
        self.setAIMoveGrid(self.aiSetting1, grid1)

        # Set rest of ally placements
        candidates = sorted(vacant)
        points = set()
        while len(points) < 14:
            pt = random.sample(grid1, 1)[0]
            n = random.randint(8, 15)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 20:
                points = set()
        outline = self.mapGrid.outlineGrid(points, candidates, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Set all ally positions
        points = sorted(points)
        allyPoints = sorted(allyPoints)
        self.setPlayerPositions(allyPoints + points)
        random.shuffle(allyPoints)
        self.setUnitTable(allyPoints) # Ensure Syranoa ends up near Symon
        outline = self.mapGrid.outlineGrid(allyPoints, vacant, length=1)
        vacant = vacant.difference(allyPoints).difference(outline)
        outline = self.mapGrid.outlineGrid(points, vacant, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Place swords in aiSetting1
        grid1 = sorted(set(grid1).intersection(vacant))
        if len(grid1) < 20:
            grid1 = sorted(vacant)
        attempts = 0
        points = set()
        while True:
            pt = random.sample(grid1, 1)[0]
            n = random.randint(5, 15)
            rect = self.mapGrid.randomRectangle(pt, n, grid1)
            points.update(rect)
            if len(points) > 15:
                break
            attempts += 1
            if attempts > 100 and len(points) > len(self.swds):
                break
        self.setPositions(points, self.swds)
        vacant = vacant.difference(points)

        # Then the rest
        candidates = sorted(vacant)
        points = set()
        while len(points) < len(self.enemies) * 4:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(5, len(self.enemies) * 4)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, self.enemies)

        self.setPCDirections(allies=self.symon)
        self.setEnemyDirections()

class MS15_X31_P1(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms15_x31_battle_01', 1, 'ms15_x31_battle_S_01')

        patriatte = self.enemyPositions[0] # AISetting_Boss1 -> AISetting_Boss2 -> AISetting_Boss3
        bok1 = self.enemyPositions[1]
        swd1 = self.enemyPositions[2]
        swd2 = self.enemyPositions[3] # AISetting_Right -> AISetting_Normal
        spr1 = self.enemyPositions[4]
        spr2 = self.enemyPositions[5]
        spr3 = self.enemyPositions[6] # AISetting_Right -> AISetting_Normal
        rod1 = self.enemyPositions[7] # AISetting_Support
        swd3 = self.enemyPositions[8]
        swd4 = self.enemyPositions[9]
        bok2 = self.enemyPositions[10]
        bow1 = self.enemyPositions[11]
        swd5 = self.enemyPositions[12]
        bow2 = self.enemyPositions[13]
        rod2 = self.enemyPositions[14]
        assert len(self.enemyPositions) == 15

        self.boss = [
            patriatte, rod1, bok1,
        ]

        self.enemiesAnywhere = [
            swd1, swd2, spr1, spr2, spr3,
            swd3, swd4, bok2, bow1, swd5,
            bow2, rod2,
        ]

        self.aiSettingBoss1 = 27
        self.aiSettingBoss2 = 28
        self.aiSettingBoss3 = 29
        

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[2].getArg(2) == 'AISetting_Right'
        assert funcs[3].getArg(2) == 'AISetting_Right'
        funcs[2].setArg(2, 'AISetting_Normal')
        funcs[3].setArg(2, 'AISetting_Normal')

        # Setting grids
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            boss3Grid = self.mapGrid.randomRectangle(pt, 250, candidates)
            if len(boss3Grid) > 200:
                break

        attempts = 0
        outline = self.mapGrid.outlineGrid(boss3Grid, candidates, length=2)
        if len(outline) < 5: # I doubt this is necessary
            outline = boss3Grid
        while True:
            pt = random.sample(outline, 1)[0]
            boss2Grid = self.mapGrid.randomRectangle(pt, 200, candidates)
            notBoss3 = sorted(set(boss2Grid).difference(boss3Grid))
            if len(boss2Grid) > 150 and len(notBoss3) > 20:
                break
            attempts += 1
            if attempts > 100:
                break

        if len(notBoss3) == 0:
            notBoss3 = boss2Grid

        pt = random.sample(notBoss3, 1)[0]
        boss1Grid = self.mapGrid.randomRectangle(pt, 5, candidates)

        self.setAIMoveGrid(self.aiSettingBoss1, boss1Grid)
        self.setAIMoveGrid(self.aiSettingBoss2, boss2Grid)
        self.setAIMoveGrid(self.aiSettingBoss3, boss3Grid)

        # Pick enemy points
        candidates = sorted(vacant)
        outline = self.mapGrid.outlineGrid(boss1Grid, candidates, length=2)
        outlineBoss1Grid = self.mapGrid.outlineGrid(boss1Grid, candidates, length=3)
        points = boss1Grid + outline
        self.setPositions(points, self.boss)
        vacant = vacant.difference(points)

        candidates = sorted(vacant)
        points = set()
        while len(points) < 4*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(5, 2*len(self.enemiesAnywhere))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesAnywhere)
        outline = self.mapGrid.outlineGrid(points, candidates, length=2)
        vacant = vacant.difference(points).difference(outline).difference(outlineBoss1Grid)

        # Pick PC points
        candidates = sorted(vacant.intersection(boss3Grid)) # Bias it towards grid with enemies, at least a little!
        if len(candidates) < 50:
            candidates = sorted(vacant)
        points = set()
        while len(points) < 12:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(8, 13)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points)                
        
        self.setPCDirections()
        self.setEnemyDirections()


class MS15_X31_P2(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms15_x31_battle_02', 1, 'ms15_x31_battle_S_02')

        patriatte = self.enemyPositions[0] # AISetting_Boss1 -> AISetting_Boss2 -> AISetting_Boss3
        bok1 = self.enemyPositions[1]
        swd1 = self.enemyPositions[2]
        swd2 = self.enemyPositions[3] # AISetting_Right -> AISetting_Normal
        spr1 = self.enemyPositions[4]
        spr2 = self.enemyPositions[5]
        spr3 = self.enemyPositions[6] # AISetting_Right -> AISetting_Normal
        rod1 = self.enemyPositions[7] # AISetting_Support
        swd3 = self.enemyPositions[8]
        swd4 = self.enemyPositions[9]
        bok2 = self.enemyPositions[10]
        bow1 = self.enemyPositions[11]
        swd5 = self.enemyPositions[12]
        bow2 = self.enemyPositions[13]
        rod2 = self.enemyPositions[14]
        assert len(self.enemyPositions) == 15

        self.boss = [
            patriatte, rod1, bok1,
        ]

        self.enemiesAnywhere = [
            swd1, swd2, spr1, spr2, spr3,
            swd3, swd4, bok2, bow1, swd5,
            bow2, rod2,
        ]

        self.aiSettingBoss1 = 31
        self.aiSettingBoss2 = 32
        self.aiSettingBoss3 = 33

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[2].getArg(2) == 'AISetting_Right'
        assert funcs[3].getArg(2) == 'AISetting_Right'
        funcs[2].setArg(2, 'AISetting_Normal')
        funcs[3].setArg(2, 'AISetting_Normal')

        # Setting grids
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            boss3Grid = self.mapGrid.randomRectangle(pt, 250, candidates)
            if len(boss3Grid) > 200:
                break

        attempts = 0
        outline = self.mapGrid.outlineGrid(boss3Grid, candidates, length=2)
        if len(outline) < 5: # I doubt this is necessary
            outline = boss3Grid
        while True:
            pt = random.sample(outline, 1)[0]
            boss2Grid = self.mapGrid.randomRectangle(pt, 200, candidates)
            notBoss3 = sorted(set(boss2Grid).difference(boss3Grid))
            if len(boss2Grid) > 150 and len(notBoss3) > 20:
                break
            attempts += 1
            if attempts > 100:
                break

        if len(notBoss3) == 0:
            notBoss3 = boss2Grid

        pt = random.sample(notBoss3, 1)[0]
        boss1Grid = self.mapGrid.randomRectangle(pt, 5, candidates)

        self.setAIMoveGrid(self.aiSettingBoss1, boss1Grid)
        self.setAIMoveGrid(self.aiSettingBoss2, boss2Grid)
        self.setAIMoveGrid(self.aiSettingBoss3, boss3Grid)

        # Pick enemy points
        candidates = sorted(vacant)
        outline = self.mapGrid.outlineGrid(boss1Grid, candidates, length=2)
        outlineBoss1Grid = self.mapGrid.outlineGrid(boss1Grid, candidates, length=3)
        points = boss1Grid + outline
        self.setPositions(points, self.boss)
        vacant = vacant.difference(points)

        candidates = sorted(vacant)
        points = set()
        while len(points) < 4*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(5, 2*len(self.enemiesAnywhere))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesAnywhere)
        outline = self.mapGrid.outlineGrid(points, candidates, length=2)
        vacant = vacant.difference(points).difference(outline).difference(outlineBoss1Grid)

        # Pick PC points
        candidates = sorted(vacant.intersection(boss3Grid)) # Bias it towards grid with enemies, at least a little!
        if len(candidates) < 50:
            candidates = sorted(vacant)
        points = set()
        while len(points) < 12:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(8, 13)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points)                
        
        self.setPCDirections()
        self.setEnemyDirections()

class MS15_X32(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms15_x32_battle_01', 1, 'ms15_x32_battle_S_01')

        travis = self.enemyPositions[0] # AISetting_Boss1
        rod3 = self.enemyPositions[1] # AISetting_Support1
        dag1 = self.enemyPositions[2] # AISetting_Mob2 -> AISetting_Normal (-> AISetting_Normal)
        dag2 = self.enemyPositions[3] # AISetting_Mob2 -> ... (-> AISetting_Normal)
        dag3 = self.enemyPositions[4] # AISetting_Dag0 -> ... (-> AISetting_Normal)
        bow1 = self.enemyPositions[5]
        bow2 = self.enemyPositions[6] # ... -> ... (-> AISestting_Normal)
        bow3 = self.enemyPositions[7] # AISetting_Bow2
        bok1 = self.enemyPositions[8] # AISetting_Mob3 -> ... (-> AISetting_Normal)
        rod1 = self.enemyPositions[9] # AISetting_Mob3
        rod2 = self.enemyPositions[10] # AISetting_Mob1 -> AISetting_Support1
        clb1 = self.enemyPositions[11] # AISetting_Mob2 -> AISetting_Normal (-> AISetting_Normal)
        dag4 = self.enemyPositions[12] # AISetting_Mob2 -> AISetting_Normal
        bok2 = self.enemyPositions[13] # AISetting_Mob2 -> AISetting_Normal
        clb2 = self.enemyPositions[14] # AISetting_Normal -> ... (-> AISetting_Normal)
        assert len(self.enemyPositions) == 15

        self.mobs = {
            'DAG1': dag1,
            'DAG2': dag2,
            'BOK1': bok1,
            'ROD1': rod1,
            'ROD2': rod2,
            'CLB1': clb1,
            'DAG4': dag4,
            'BOK2': bok2,
        }

        self.bows = [ # Sample from bow1 grid; don't change bow ai
            bow1, bow2, bow3,
        ]

        self.enemiesAnywhere = [ # Keep as 1 cluster; dag3 is dag0 AI, close enough to everywhere....
            travis, rod3, clb2, dag3,
        ]

        self.aiBow1 = 79
        self.aiMob1 = 90
        self.aiMob2 = 91
        self.aiMob3 = 89
         
        changeAISettings = self.battle.getLocalFunction('ChangeAISettings')[0]
        self.changeAISettings = {}
        for setting in changeAISettings:
            n = setting.getArg(1)
            self.changeAISettings[n] = setting

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Change boss ai to Boss2
        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[0].getArg(1) == 'UNIT_MASTER_CH_P014'
        funcs[0].setArg(2, 'AISetting_Boss2')

        # Set PCs
        points = set()
        candidates = sorted(vacant)
        while len(points) < 12:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Set mobs
        grid1 = sorted(vacant.intersection(self.getAIMoveGrid(self.aiMob1)))
        grid1 += self.mapGrid.outlineGrid(grid1, vacant)
        grid2 = sorted(vacant.intersection(self.getAIMoveGrid(self.aiMob2)))
        grid2 += self.mapGrid.outlineGrid(grid2, vacant)
        grid3 = sorted(vacant.intersection(self.getAIMoveGrid(self.aiMob3)))
        grid3 += self.mapGrid.outlineGrid(grid3, vacant)
        count = 0
        while True:
            while True:
                n1 = []
                n2 = []
                n3 = []
                for key, enemy in self.mobs.items():
                    r = random.random()
                    if r < 1./3:
                        n1.append((key, enemy))
                    elif r < 2./3:
                        n2.append((key, enemy))
                    else:
                        n3.append((key, enemy))
                # Make sure there's enough space
                if len(n1) <= len(grid1) and len(n2) <= len(grid2) and len(n3) <= len(grid3):
                    break

            points1 = random.sample(grid1, len(n1))
            vacant = vacant.difference(points1)
            points2 = []
            while len(points2) < len(n2):
                count += 1
                pt = random.sample(grid2, 1)[0]
                if pt in vacant:
                    vacant.remove(pt)
                    points2.append(pt)
                if count%1000 == 0:
                    break
            if count%1000 == 0:
                continue
            
            points3 = []
            while len(points3) < len(n3):
                count += 1
                pt = random.sample(grid3, 1)[0]
                if pt in vacant:
                    vacant.remove(pt)
                    points3.append(pt)
                if count%1000 == 0:
                    break
            if count%1000 == 0:
                continue

            assert len(points1) == len(n1)
            assert len(points2) == len(n2)
            assert len(points3) == len(n3)
            break

        for i, (key, enemy) in enumerate(n1):
            self.changeAISettings[key].setArg(2, 'AISetting_Mob1')
            enemy.X, enemy.Y = points1[i]
        for i, (key, enemy) in enumerate(n2):
            self.changeAISettings[key].setArg(2, 'AISetting_Mob2')
            enemy.X, enemy.Y = points2[i]
        for i, (key, enemy) in enumerate(n3):
            self.changeAISettings[key].setArg(2, 'AISetting_Mob3')
            enemy.X, enemy.Y = points3[i]

        # Set archers
        grid = sorted(vacant.intersection(self.getAIMoveGrid(self.aiBow1)))
        points = random.sample(grid, len(self.bows))
        self.setPositions(points, self.bows)
        vacant = vacant.difference(points)

        # Set remaining enemies
        points = set()
        candidates = sorted(vacant)
        while len(points) < len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, 20, candidates)
            points.update(rect)
        vacant = vacant.difference(points)
        self.setPositions(points, self.enemiesAnywhere)

        self.setPCDirections()
        self.setEnemyDirections()

class MS15_X33(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms15_x33_battle_01', 1, 'ms15_x33_battle_S_01')

        trish = self.enemyPositions[0] # AISetting_Boss2
        dag1 = self.enemyPositions[1] # AISetting_Mob1
        dag2 = self.enemyPositions[2] # AISetting_Mob1
        dag3 = self.enemyPositions[3] # AISetting_Mob2
        dag4 = self.enemyPositions[4] # AISetting_Mob2
        dag5 = self.enemyPositions[5]
        rod1 = self.enemyPositions[6] # AISetting_Support
        rod2 = self.enemyPositions[7] # AISetting_Mob2
        bow1 = self.enemyPositions[8] # AISetting_Mob1
        bow2 = self.enemyPositions[9] # AISetting_Mob3
        bow3 = self.enemyPositions[10]
        clb1 = self.enemyPositions[11] # AISetting_Mob1
        clb2 = self.enemyPositions[12] # AISetting_Mob2
        bok1 = self.enemyPositions[13] # AISetting_Mob1
        bok2 = self.enemyPositions[14] # AISetting_Mob2
        assert len(self.enemyPositions) == 15

        self.mobs = {
            'DAG1': dag1,
            'DAG2': dag2,
            'DAG3': dag3,
            'DAG4': dag4,
            'BOW1': bow1,
            'BOW2': bow2,
            'CLB1': clb1,
            'CLB2': clb2,
            'BOK1': bok1,
            'BOK2': bok2,
        }

        self.enemiesAnywhere = [
            dag5, bow3, rod1, rod2,
        ]

        self.boss = [
            trish,
        ]

        # NOTES
        # For mobs, only do 1 and 2
        # - mob 3 is extremely small and only really suitable for bows (and maybe boks)
        # Start trish in AISetting_Boss2

        self.aiBoss2 = 40
        self.aiMob1 = 43
        self.aiMob2 = 44
        self.aiMob3 = 45
        self.aiSupport = 46

        changeAISettings = self.battle.getLocalFunction('ChangeAISettings')[0]
        self.changeAISettings = {}
        for setting in changeAISettings:
            n = setting.getArg(1)
            self.changeAISettings[n] = setting

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Set PCs
        points = set()
        candidates = sorted(vacant)
        while len(points) < 12:
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)
        self.setPlayerPositions(points)

        # Set trish
        points = set()
        candidates = sorted(vacant.intersection(self.getAIMoveGrid(self.aiBoss2)))
        points = random.sample(candidates, len(self.boss))
        vacant = vacant.difference(points)
        self.setPositions(points, self.boss)

        # Set mobs
        grid1 = sorted(vacant.intersection(self.getAIMoveGrid(self.aiMob1)))
        grid1 += self.mapGrid.outlineGrid(grid1, vacant)
        grid2 = sorted(vacant.intersection(self.getAIMoveGrid(self.aiMob2)))
        grid2 += self.mapGrid.outlineGrid(grid2, vacant)
        grid3 = sorted(vacant.intersection(self.getAIMoveGrid(self.aiMob3)))
        grid3 += self.mapGrid.outlineGrid(grid3, vacant)
        count = 0
        while True:
            while True:
                n1 = []
                n2 = []
                n3 = []
                for key, enemy in self.mobs.items():
                    r = random.random()
                    if r < 1./3:
                        n1.append((key, enemy))
                    elif r < 2./3:
                        n2.append((key, enemy))
                    else:
                        n3.append((key, enemy))
                # Make sure there's enough space
                if len(n1) <= len(grid1) and len(n2) <= len(grid2) and len(n3) <= len(grid3):
                    break

            points1 = random.sample(grid1, len(n1))
            vacant = vacant.difference(points1)
            points2 = []
            while len(points2) < len(n2):
                count += 1
                pt = random.sample(grid2, 1)[0]
                if pt in vacant:
                    vacant.remove(pt)
                    points2.append(pt)
                if count%1000 == 0:
                    break
            if count%1000 == 0:
                continue
            
            points3 = []
            while len(points3) < len(n3):
                count += 1
                pt = random.sample(grid3, 1)[0]
                if pt in vacant:
                    vacant.remove(pt)
                    points3.append(pt)
                if count%1000 == 0:
                    break
            if count%1000 == 0:
                continue

            assert len(points1) == len(n1)
            assert len(points2) == len(n2)
            assert len(points3) == len(n3)
            break

        for i, (key, enemy) in enumerate(n1):
            self.changeAISettings[key].setArg(2, 'AISetting_Mob1')
            enemy.X, enemy.Y = points1[i]
        for i, (key, enemy) in enumerate(n2):
            self.changeAISettings[key].setArg(2, 'AISetting_Mob2')
            enemy.X, enemy.Y = points2[i]
        for i, (key, enemy) in enumerate(n3):
            self.changeAISettings[key].setArg(2, 'AISetting_Mob3')
            enemy.X, enemy.Y = points3[i]

        # Set remaining enemies
        points = set()
        candidates = sorted(vacant)
        while len(points) < 4*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, 10, candidates)
            points.update(rect)
        vacant = vacant.difference(points)
        self.setPositions(points, self.enemiesAnywhere)


        self.setPCDirections()
        self.setEnemyDirections()

class MS16_X34(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms16_x34_battle_01', 1, 'ms16_x34_battle_S')

        self.gimmick = self.battleCommon.getLocalFunction('CreateGimmickData')[0]
        self.bomb = ENEMYPOSITION(self.gimmick, self.mapGrid)
        
        swd1 = self.enemyPositions[0] # AI_DEEP
        swd2 = self.enemyPositions[1]
        swd3 = self.enemyPositions[2]
        spr1 = self.enemyPositions[3]
        spr2 = self.enemyPositions[4]
        bok1 = self.enemyPositions[5]
        bok2 = self.enemyPositions[6] # AI_DEEP
        rod1 = self.enemyPositions[7]
        bow1 = self.enemyPositions[8]
        bow2 = self.enemyPositions[9]
        assert len(self.enemyPositions) == 10

        self.deep = [
            swd1, bok2,
        ]

        self.enemiesAnywhere = [
            swd2, swd3, spr1, spr2,
            bok1, rod1, bow1, bow2,
        ]

        self.aiDeep = 9

    def random(self):
        self.isRandomized = True
        carts = [
            # Slots with carts
            (6, 20), (10, 16), (17, 4), (4, 15),
            (19, 14), (21, 12), (21, 9), (24, 5),
            (27, 6), (21, 20),
            # Empty slots for carts
            (11,19), (9,9), (6,10), (7,4), (17,8),
            (23,18), (28,16), (31,15), (33,14), (30,11),
        ]
        vacant = set(self.mapGrid.getAccessible(0, 16)).difference(carts)

        # Reinforcements
        def validEdgePoint():
            pt = self.mapGrid.randomEdgePoint()
            if pt in vacant:
                return pt
            return None
        
        candidates = sorted(vacant)
        while True:
            reinforcements = []

            pt = validEdgePoint()
            if not pt: continue
            reinforcements += self.mapGrid.flatLine(candidates, length=3, pt=pt)

            pt = validEdgePoint()
            if not pt: continue
            reinforcements += self.mapGrid.flatLine(candidates, length=3, pt=pt)

            pt = validEdgePoint()
            if not pt: continue
            reinforcements += self.mapGrid.flatLine(candidates, length=3, pt=pt)

            if len(set(reinforcements)) == 9:
                break

        funcs = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        self.setWaki(funcs[0], reinforcements[1])
        self.setWaki(funcs[1], reinforcements[4])
        self.setWaki(funcs[2], reinforcements[7])
        self.mapGrid.clearSpecs('Reinforce')
        self.mapGrid.addSpec('Reinforce', reinforcements)

        # First bomb for the tutorial
        bombarea = self.mapGrid.getIdxs('bombarea')
        bombarea.remove((20,20)) # Inaccessible point!
        bombPt = random.sample(bombarea, 1)[0]
        self.bomb.X, self.bomb.Y = bombPt
        vacant.remove(bombPt)

        bombcamera = self.battle.getLocalFunction('ChangeStageCameraToMapGrid')[0][0]
        bombcamera.setArg(1, float(bombPt[0]))
        bombcamera.setArg(2, float(bombPt[1]))
        ct = bombcamera.getArg(8)
        t = ct.getTable()[0]
        if bombPt[0] >= 20:
            t['Pitch'] = 45.0
            t['Yaw'] = 500.0
        elif bombPt[1] >= 12:
            t['Pitch'] = 45.0
        ct.setTable(t)

        # Set deep grid and enemies
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            deepGrid = self.mapGrid.randomRectangle(pt, 50, candidates)
            if 40 <= len(deepGrid) <= 100:
                break

        self.setAIMoveGrid(self.aiDeep, deepGrid)
        pts = random.sample(deepGrid, 2)
        self.setPositions(pts, self.deep)
        outline = self.mapGrid.outlineGrid(pts, vacant, length=3)
        vacant = vacant.difference(pts).difference(outline)

        # PC grid(s)
        outline = self.mapGrid.outlineGrid(deepGrid, sorted(vacant), length=5)
        candidates = sorted(vacant.difference(deepGrid).difference(outline))
        while True:
            points = set()
            while len(points) < 10:
                pt = random.sample(candidates, 1)[0]
                rect = self.mapGrid.randomRectangle(pt, 12, candidates)
                points.update(rect)
            if len(points) >= 10 and len(points) < 16:
                break
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=3)
        vacant = vacant.difference(points).difference(outline)
        
        # Enemy positions
        self.setPositions(vacant, self.enemiesAnywhere)

        self.setPCDirections()
        self.setEnemyDirections()


class MS17S_X38(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms17s_x38_battle_01', 0, 'ms17s_x38_battle_S_01')

        gimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        self.switchA = ENEMYPOSITION(gimmicks[0], self.mapGrid)
        self.switchB = ENEMYPOSITION(gimmicks[1], self.mapGrid)
        self.switchC = ENEMYPOSITION(gimmicks[2], self.mapGrid)
        self.switchD = ENEMYPOSITION(gimmicks[3], self.mapGrid)

        exharme = self.enemyPositions[0] # AISetting1 -> AISetting3
        rod1 = self.enemyPositions[1] # AISetting1 -> AISetting5
        sld1 = self.enemyPositions[2]
        bow1 = self.enemyPositions[3]
        spr2 = self.enemyPositions[4]
        bok1 = self.enemyPositions[5]
        spr1 = self.enemyPositions[6] # AISetting2 -> AISetting5
        sld2 = self.enemyPositions[7] # AISetting2 -> AISetting5
        bow2 = self.enemyPositions[8] # AISetting2 -> AISetting5
        bow3 = self.enemyPositions[9] # AISetting2 -> AISetting5
        dag1 = self.enemyPositions[10] # AISetting2 -> AISetting5
        bok2 = self.enemyPositions[11] # AISetting2 -> AISetting5
        rod2 = self.enemyPositions[12] # AISetting2 -> AISetting5
        assert len(self.enemyPositions) == 13

        self.boss = [
            exharme, rod1,
        ]

        self.enemiesAnywhere = [
            sld1, spr2, bok1,
            spr1, sld2, dag1, bok2, rod2,
            bow1, bow2, bow3,
        ]

        self.aiSetting1 = 26

    def updateEnforcedPCs(self, mapPCs):
        pass

    def random(self):
        self.isRandomized = True
        vacant = set(filter(lambda pt: pt[0] <= 20, self.mapGrid.getValid())).difference([
            (16, 23), (17, 23), (18, 23), (19, 23), # No clue why these are impassable
        ])
        easilyAccessible = self.mapGrid.bfs((0, 23), 1000, vacant)
        vacant = vacant.intersection(easilyAccessible)
        allPoints = set(vacant)

        eventA = self.mapGrid.getIdxs('Event_A')
        eventB = self.mapGrid.getIdxs('Event_B')
        eventC = self.mapGrid.getIdxs('Event_C')
        eventD = self.mapGrid.getIdxs('Event_D')

        # Set switches
        candidates = sorted(vacant.difference(eventA).difference(eventB).difference(eventC).difference(eventD))
        outlineA = self.mapGrid.outlineGrid(eventA, candidates, length=4)
        outlineB = self.mapGrid.outlineGrid(eventB, candidates, length=4)
        outlineC = self.mapGrid.outlineGrid(eventC, candidates, length=4)
        outlineD = self.mapGrid.outlineGrid(eventD, candidates, length=4)
        while True:
            ptA = random.sample(outlineA, 1)[0]
            ptB = random.sample(outlineB, 1)[0]
            ptC = random.sample(outlineC, 1)[0]
            ptD = random.sample(outlineD, 1)[0]
            if len(set([ptA, ptB, ptC, ptD])) == 4:
                break
        self.switchA.X, self.switchA.Y = ptA
        self.switchB.X, self.switchB.Y = ptB
        self.switchC.X, self.switchC.Y = ptC
        self.switchD.X, self.switchD.Y = ptD
        vacant = vacant.difference([ptA, ptB, ptC, ptD])
        cameras = self.battle.getLocalFunction('ChangeStageCameraToMapGrid')
        cursor = self.battle.getLocalFunction('MoveBattleCursor')
        def setSwitchOverview(pt, func):
            func.setArg(1, float(pt[0]))
            func.setArg(2, float(pt[1]))
        setSwitchOverview(ptB, cameras[0])
        setSwitchOverview(ptB, cameras[1])
        setSwitchOverview(ptB, cursor[0])
        setSwitchOverview(ptC, cameras[2])
        setSwitchOverview(ptC, cursor[1])
        setSwitchOverview(ptD, cameras[3])
        setSwitchOverview(ptD, cursor[2])
        setSwitchOverview(ptA, cameras[4])
        setSwitchOverview(ptA, cursor[3])

        # Set PCs
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            pcPoints = self.mapGrid.randomRectangle(pt, 15, candidates)
            if len(pcPoints) >= 15 and len(pcPoints) < 40:
                break
        self.setPlayerPositions(pcPoints)
        outline = self.mapGrid.outlineGrid(pcPoints, candidates)
        vacant = vacant.difference(pcPoints).difference(outline)

        # Set wakis
        candidates = sorted(vacant.difference(eventA).difference(eventB).difference(eventC).difference(eventD))
        # Ensure waki cannot start on NE roof!
        candidates = [pt for pt in candidates if not (pt[0] >= 14 and pt[1] <= 6)]
        edges = self.mapGrid.edgesOfGrid(candidates)
        points = random.sample(edges, 6)
        funcs = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        for p, f in zip(points, funcs):
            self.setWaki(f, p)

        # Set Exharme as far as possible from PCs
        pt = self.mapGrid.clusterMean(pcPoints)
        candidates = sorted(vacant.difference(eventA).difference(eventB).difference(eventC).difference(eventD))
        tol = 0
        while True:
            bossPt = self.mapGrid.greatestDistance(pt, grid=candidates, tol=tol)
            if bossPt:
                bossGrid = self.mapGrid.bfs(bossPt, 10, candidates)
                if len(bossGrid) > 4:
                    break
            tol += 1
        self.setPositions(bossGrid, self.boss)
        vacant = vacant.difference(bossGrid)
        self.setAIMoveGrid(self.aiSetting1, bossGrid)

        # Set enemies
        candidates = sorted(vacant)
        tol = 0
        count = 0
        while True:
            d = random.randint(2, 7)
            pt = self.mapGrid.randomNearbyPoint(bossPt, d, candidates, dh=20, tol=tol)
            count += 1
            if count % 50 == 0:
                tol += 1
            if pt is None:
                continue
            enemyPoints = self.mapGrid.randomRectangle(pt, 20, candidates)
            if len(enemyPoints) >= 20:
                break
        self.setPositions(enemyPoints, self.enemiesAnywhere)
        vacant.difference(enemyPoints)

        # Changes AI for most enemies if designated enemy lands on this grid
        candidates = sorted(allPoints)
        tol = 0
        while True:
            pt = self.mapGrid.greatestDistance(bossPt, grid=candidates, tol=tol)
            if pt:
                break
            tol += 1
        allfull = self.mapGrid.bfs(pt, 60, candidates)
        self.mapGrid.clearSpecs('allfull')
        self.mapGrid.addSpec('allfull', allfull)

        self.setPCDirections()
        self.setEnemyDirections()

class MS18B_X39(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms18b_x39_battle_01', 1, 'ms18b_x39_battle_S_01')

        self.lub_gimmicks = [
            Lub(pak, "ms18b_x39_research_01_change_map.lub"),
            Lub(pak, "ms18b_x39_research_01_drama_sel.lub"),
            Lub(pak, "ms18b_x39_battle_01_before.lub"),
        ]

        clarus = self.enemyPositions[0] # AISetting1 -> AISetting2
        rod1 = self.enemyPositions[1] # AISetting1 -> AISetting2
        rid2 = self.enemyPositions[2]
        rid3 = self.enemyPositions[3]
        rid4 = self.enemyPositions[4]
        rid5 = self.enemyPositions[5]
        rid6 = self.enemyPositions[6]
        rid7 = self.enemyPositions[7]
        rid12 = self.enemyPositions[8]
        rid8 = self.enemyPositions[9]
        rid9 = self.enemyPositions[10]
        rid10 = self.enemyPositions[11]
        rid11 = self.enemyPositions[12]
        rid13 = self.enemyPositions[13]
        assert len(self.enemyPositions) == 14

        self.boss = [ # Spawn in a rectangle of 30 tiles
            clarus, rod1,
        ]

        self.enemiesAnywhere = [
            rid2, rid3, rid4, rid5, rid6, rid7,
            rid12, rid8, rid9, rid10, rid11, rid13,
        ]

    def update(self):
        super().update()
        if self.isRandomized:
            for lub in self.lub_gimmicks:
                lub.update()

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Pick group(s) for PCs
        candidates = sorted(vacant)
        pt = self.mapGrid.randomEdgePoint()
        while True:
            n = random.randint(20, 40)
            gridPC = self.mapGrid.randomRectangle(pt, n, candidates)
            if 20 < len(gridPC) < 40:
                break
        self.setPlayerPositions(gridPC)
        vacant = vacant.difference(gridPC)
        gridPCOutline = self.mapGrid.outlineGrid(gridPC, vacant, length=1)

        # Set barricades
        def getBarracks(gridPC, vacant, nlines=3):
            n = random.randint(1, 2)
            gridPC += self.mapGrid.outlineGrid(gridPC, vacant, length=n)
            outline = set(self.mapGrid.outlineGrid(gridPC, vacant))
            while True:
                barracks = set()
                for _ in range(nlines):
                    pt = random.sample(outline, 1)[0]
                    n = random.randint(3, 6)
                    line = self.mapGrid.randomWalkGrid(n, outline)
                    barracks.update(line)
                if len(barracks) < len(outline):
                    break
            # empty = set()
            # for _ in range(ngaps):
            #     count = random.randint(3, 5)
            #     pt = random.sample(sorted(outline), 1)[0]
            #     rect = self.mapGrid.randomRectangle(pt, count, outline)
            #     empty.update(rect)
            # barracks = outline.difference(empty)
            gridPC += outline
            return sorted(barracks)
        
        barracks = getBarracks(gridPC, vacant, nlines=random.randint(1, 3))
        barracks += getBarracks(gridPC, vacant, nlines=random.randint(1, 4))
        gimmicks = self.battleCommon.getLocalFunction('CreateGimmickData')
        positions = [ENEMYPOSITION(g, self.mapGrid) for g in gimmicks]
        friends = self.battle.getLocalFunction('SetMapGimmickUnitCampForAI')
        self.setGimmickPositions(barracks, gimmicks, positions, friends)
        vacant = vacant.difference(gridPCOutline).difference(barracks)
        
        # Spawn enemies
        while True:
            pt = self.mapGrid.randomEdgePoint()
            if pt in vacant:
                break
        zouenDefault = self.mapGrid.getIdxs('Zouen01')
        zouenNew = self.mapGrid.bfs(pt, len(zouenDefault), vacant)
        self.mapGrid.clearSpecs('Zouen01')
        self.mapGrid.addSpec('Zouen01', zouenNew)
        func = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')[0]
        self.setWaki(func, pt)

        # Place boss in rectangle
        candidates = sorted(vacant)
        while True:
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, 20, candidates)
            if len(rect) > len(self.boss):
                break
        self.setPositions(rect, self.boss)
        vacant = vacant.difference(rect)

        # Place remaining enemies
        candidates = sorted(vacant)
        points = set()
        while len(points) < 3*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, len(self.enemiesAnywhere), candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesAnywhere)        

        self.setPCDirections()
        self.setEnemyDirections()

class MS18R_X40(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms18r_x40_battle_01', 0, 'ms18r_x40_battle_S_01')

        # Exharme
        self.ally = self.enemyPositions.pop(0) # AISetting6
        
        sycras = self.enemyPositions[0] # AISetting2
        bow1 = self.enemyPositions[1] # AISetting1 -> AISetting3
        bow2 = self.enemyPositions[2]
        bow3 = self.enemyPositions[3]
        bow4 = self.enemyPositions[4]
        bow5 = self.enemyPositions[5] # AISetting5 -> AISetting3
        bow6 = self.enemyPositions[6] # AISetting1 -> AISetting3
        swd1 = self.enemyPositions[7]
        swd2 = self.enemyPositions[8] # AISetting1 -> AISetting3
        sld1 = self.enemyPositions[9] # AISetting1 -> AISetting3
        sld2 = self.enemyPositions[10]
        rod1 = self.enemyPositions[11] # AISetting2
        bok2 = self.enemyPositions[12]
        bok3 = self.enemyPositions[13] # AISetting1
        assert len(self.enemyPositions) == 14

        self.boss = [
            sycras, rod1,
        ]

        # Consider setting bow5 AI to AISetting1 by default
        self.enemiesAnywhere = [ # Keep them high!
            bow1, bow2, bow3, bow4, bow5, bow6,
            swd1, swd2, sld1, sld2, bok2, bok3,
        ]

        self.aiSetting1 = 27
        self.aiSetting2 = 28
        self.aiSetting3 = 29
        self.aiSetting4 = 30
        self.aiSetting5 = 31

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Change this AI setting to everywhere
        self.setAIMoveGrid(self.aiSetting3, vacant)

        # Set PCs
        points = set()
        ground = sorted(filter(lambda x: self.mapGrid.getHeight(*x) == 1, vacant))
        ptRef = random.sample(ground, 1)[0]
        count = 0
        while len(points) < 12:
            d = random.randint(2, 8)
            pt = self.mapGrid.randomNearbyPoint(ptRef, d, vacant, dh=10, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, ground)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points, ally=self.ally)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Set boss enemies, grids specs, and spawns
        notground = sorted(filter(lambda x: self.mapGrid.getHeight(*x) > 1, vacant))
        while True:
            bossPt = random.sample(notground, 1)[0]
            bossGrid = self.mapGrid.bfs(bossPt, 20, notground, d=5)
            if len(bossGrid) > 2*len(self.boss):
                break
        self.setPositions(bossGrid, self.boss)
        aiGrid = self.mapGrid.bfs(bossPt, 160, vacant, d=20)
        self.setAIMoveGrid(self.aiSetting2, aiGrid)
        vacant = vacant.difference(bossGrid)
        
        outline = self.mapGrid.outlineGrid(bossGrid, vacant, length=5)
        self.mapGrid.clearSpecs('ambush')
        self.mapGrid.addSpec('ambush', set(outline + aiGrid))

        grid = sorted(bossGrid + outline)
        pt = random.sample(grid, 1)[0]
        func = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')[0]
        self.setWaki(func, pt)

        # Pick some enemies to be in the outline
        e = random.sample(self.enemiesAnywhere, random.randint(2, len(self.enemiesAnywhere)//2))
        enem = list(filter(lambda x: x not in e, self.enemiesAnywhere))
        self.setPositions(outline, e)
        vacant = vacant.difference(outline)
        
        # Place the rest anywhere above ground
        ptRef = self.mapGrid.clusterMean([(p.X, p.Y) for p in self.pcPositions])
        notground = sorted(filter(lambda x: self.mapGrid.getHeight(*x) > 1, vacant))
        points = set()
        count = 0
        while len(points) < 4*len(enem):
            d = random.randint(8, 15)
            pt = self.mapGrid.randomNearbyPoint(ptRef, d, notground, dh=10, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(3, 10)
            grid = self.mapGrid.randomRectangle(pt, n, notground, d=5)
            points.update(grid)
            if len(points) > 5*len(enem):
                points = set()
                count = 0
        self.setPositions(points, enem)

        self.setPCDirections(self.ally)
        self.setEnemyDirections()

class MS18F_X41(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms18f_x41_battle_01', 1, 'ms18f_x41_battle_S_01')

        self.lyla = self.enemyPositions[0] # AI_BOSS -> AI_BOSS2 -> AI_NORMAL -> AI_BOSS3
        bow1 = self.enemyPositions[1] # AI_BEDL
        bow2 = self.enemyPositions[2] # AI_SUPPORT
        bow3 = self.enemyPositions[3] # AI_BEDR
        bok1 = self.enemyPositions[4] # AI_BEDL
        bok2 = self.enemyPositions[5] # AI_BEDR
        dag1 = self.enemyPositions[6]
        dag2 = self.enemyPositions[7]
        swd1 = self.enemyPositions[8]
        swd2 = self.enemyPositions[9]
        swd3 = self.enemyPositions[10]
        rod1 = self.enemyPositions[11] # AI_SUPPORT
        rod2 = self.enemyPositions[12] # AI_SUPPORT
        spr1 = self.enemyPositions[13]
        sld1 = self.enemyPositions[14]
        assert len(self.enemyPositions) == 15

        self.beds = {
            'BOW1': bow1,
            'BOW3': bow3,
            'BOK1': bok1,
            'BOK2': bok2,
        }

        self.enemiesAnywhere = [
            bow2, dag1, dag2, swd1, swd2, swd3,
            rod1, rod2, spr1, sld1,
        ]

        # NOTES:
        # AI_BOSS includes 2 very close points
        # points must be contained withing ChangeAI1 specs
        # No real need to modify AI_BOSS2
        self.aiBoss = 43

        changeAISettings = self.battle.getLocalFunction('ChangeAISettings')[0]
        self.changeAISettings = {}
        for setting in changeAISettings:
            n = setting.getArg(1)
            self.changeAISettings[n] = setting

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Pick Lyla's start point and AI points
        candidates = sorted(vacant)
        lylaPoint = random.sample(candidates, 1)[0]
        vacant.remove(lylaPoint)
        n = random.randint(2, 5)
        aiBossGrid = self.mapGrid.bfs(lylaPoint, n, candidates)
        vacant = vacant.difference(aiBossGrid)
        self.lyla.X, self.lyla.Y = lylaPoint
        outline = self.mapGrid.outlineGrid(aiBossGrid, vacant, length=4)
        changeAI1 = set(aiBossGrid).union(outline)
        self.mapGrid.clearSpecs('ChangeAI1')
        self.mapGrid.addSpec('ChangeAI1', changeAI1)
        vacant = vacant.difference(outline)

        # Pick points for archers and mages
        points = random.sample(sorted(vacant), len(self.beds))
        for pt, (key, enemy) in zip(points, self.beds.items()):
            enemy.X, enemy.Y = pt
            if enemy.X > 9:
                ai = 'AI_BEDR'
            elif enemy.X < 9:
                ai = 'AI_BEDL'
            else:
                ai = 'AI_BEDR' if random.random() < 0.5 else 'AI_BEDL'
            self.changeAISettings[key].setArg(2, ai)
        outline = self.mapGrid.outlineGrid(points, vacant, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Pick grids for PCs
        farPoint = self.mapGrid.greatestDistance(lylaPoint)
        points = set()
        tol = 0
        count = 0
        while len(points) < 12:
            d = random.randint(1, 4)
            pt = self.mapGrid.randomNearbyPoint(farPoint, d, vacant, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(1, len(self.pcPositions))
            rect = self.mapGrid.randomRectangle(pt, n, vacant)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Pick points for the remaining enemies
        self.setPositions(vacant, self.enemiesAnywhere)

        self.setPCDirections()
        self.setEnemyDirections()

class MS18S_X42(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms18s_x42_battle_01', 0, 'ms18s_x42_battle_S_01')

        # May want to adjust BATTLE_UNITPARAM_CH_P034 jumpdownstat
        # from 2 -> 3. Might prevent Svarag from getting trapped.
        svarog = self.enemyPositions.pop(0) # AISetting4 -> "" -> AISetting5 (turn 80)
        self.ally = svarog

        gustadolph = self.enemyPositions[0] # AISetting1 -> AISetting3
        sld1 = self.enemyPositions[1]
        sld2 = self.enemyPositions[2]
        swd1 = self.enemyPositions[3]
        rod1 = self.enemyPositions[4] # AISetting1 -> AISetting3
        rod2 = self.enemyPositions[5] # AISetting1 -> AISetting3
        bok1 = self.enemyPositions[6]
        bok2 = self.enemyPositions[7]
        swd3 = self.enemyPositions[8] # AISetting2
        bow2 = self.enemyPositions[9] # AISetting2
        swd2 = self.enemyPositions[10]
        bow1 = self.enemyPositions[11]
        rid1 = self.enemyPositions[12] # AISetting1 -> AISetting3
        rid2 = self.enemyPositions[13] # AISetting1 -> AISetting3
        assert len(self.enemyPositions) == 14

        self.boss = [
            gustadolph, rod1, rod2, rid1, rid2,
        ]

        self.enemiesAnywhere = [
            sld1, sld2, swd1, bok1, bok2, swd3, bow2, swd2, bow1,
        ]

        self.aiSetting1 = 26
        self.aiSetting2 = 27
        self.aiSetting3 = 24
        self.aiSetting4 = 25

    def updateEnforcedPCs(self, mapPCs):
        pass

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Pick 2 points some distance away. The outline.  This grid
        # will define AISetting2 and the enemies will be clustered at
        # one end.
        candidates = sorted(vacant)
        while True:
            bossPoint = random.sample(candidates, 1)[0]
            svarogPoint = random.sample(candidates, 1)[0]
            path = self.mapGrid.shortestPath(svarogPoint, bossPoint) # Might get too repetitive with the shortest path....
            if len(path) < 20:
                continue
            n = random.randint(18, 26)
            assert path[0] == bossPoint, "NOPE: WRONG END!"
            while len(path) > n:
                svarogPoint = path.pop()

            svarogGrid = self.mapGrid.bfs(svarogPoint, 60, candidates)
            if len(svarogGrid) < 40:
                continue
            outline = self.mapGrid.outlineGrid(svarogGrid, vacant)

            tmpGrid = sorted(vacant.difference(svarogGrid).difference(outline))
            if bossPoint not in tmpGrid:
                continue
            bossGrid = self.mapGrid.bfs(bossPoint, 40, tmpGrid)
            if len(bossGrid) < 30:
                continue

            break
        outline = self.mapGrid.outlineGrid(path, candidates, length=6)
        gridAI2 = sorted(set(path).union(outline))
        self.setAIMoveGrid(self.aiSetting2, gridAI2)

        # Boss group
        bossOutline = self.mapGrid.outlineGrid(bossGrid, vacant, length=3)
        bossSpec = bossGrid + bossOutline
        self.mapGrid.clearSpecs('go_N101')
        self.mapGrid.addSpec('go_N101', bossSpec)
        self.setAIMoveGrid(self.aiSetting1, bossGrid)
        self.setPositions(bossGrid, self.boss)
        vacant = vacant.difference(bossGrid) # Outline already included
        self.setAIMoveGrid(self.aiSetting4, vacant)

        # Next set ally
        self.ally.X, self.ally.Y = svarogPoint
        svarogGrid.remove(svarogPoint)

        # Next do PCs
        points = set()
        while len(points) < 16:
            pt = random.sample(svarogGrid, 1)[0]
            n = random.randint(5, 10)
            rect = self.mapGrid.randomRectangle(pt, n, svarogGrid, d=3)
            points.update(rect)
            if len(points) > 30:
                point = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=4)
        vacant = vacant.difference(points).difference(outline)

        # Finally do the remaining enemies
        candidates = sorted(vacant)
        points = set()
        while len(points) < 3*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, len(self.enemiesAnywhere)//2)
            grid = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(grid)
        self.setPositions(points, self.enemiesAnywhere)

        self.setPCDirections(self.ally)
        self.setEnemyDirections()

class MS19B_X43_P1(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms19b_x43_battle_01', 1, 'ms19b_x43_battle_S_01')

        exharme = self.enemyPositions[0] # AISetting1 -> AISetting2
        rid1 = self.enemyPositions[1]
        bok1 = self.enemyPositions[2]
        rid2 = self.enemyPositions[3]
        rid6 = self.enemyPositions[4]
        rid3 = self.enemyPositions[5]
        rid4 = self.enemyPositions[6]
        rid5 = self.enemyPositions[7]
        bow1 = self.enemyPositions[8]
        assert len(self.enemyPositions) == 9

        self.boss = [
            exharme, bok1, 
        ]

        self.enemiesAnywhere = [
            rid1, rid2, rid6, rid3, rid4, rid5, bow1,
        ]

        self.aiSettings1 = 12


    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Pick group(s) for PCs
        candidates = sorted(vacant)
        points = set()
        while len(points) < 20:
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, 15, candidates)
            points.update(rect)
            if len(points) > 40:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)
        
        # Spawn enemies
        while True:
            pt = self.mapGrid.randomEdgePoint()
            if pt in vacant:
                break
        zouenDefault = self.mapGrid.getIdxs('Zouen01')
        zouenNew = self.mapGrid.bfs(pt, len(zouenDefault), vacant)
        self.mapGrid.clearSpecs('Zouen01')
        self.mapGrid.addSpec('Zouen01', zouenNew)
        func = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')[0]
        self.setWaki(func, pt)

        # Place boss in rectangle
        candidates = sorted(vacant)
        grid = self.getAIMoveGrid(self.aiSettings1)
        while True:
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.bfs(pt, len(grid), candidates)
            if len(rect) > len(self.boss):
                break
        self.setPositions(rect, self.boss)
        self.setAIMoveGrid(self.aiSettings1, rect)
        vacant = vacant.difference(rect)

        # Place remaining enemies
        candidates = sorted(vacant)
        points = set()
        while len(points) < 4*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, len(self.enemiesAnywhere), candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesAnywhere)        

        self.setPCDirections()
        self.setEnemyDirections()

class MS19B_X43_P2(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms19b_x43_battle_02', 1, 'ms19b_x43_battle_S_02')

        heirophant = self.enemyPositions[0] # AISetting_Boss0 -> AISetting_Boss1 -> AISetting_Boss2 -> AISetting_Boss3
        hom1 = self.enemyPositions[1] # AISetting_HOM -> AISetting_Normal
        hom2 = self.enemyPositions[2] # AISetting_HOM -> AISetting_Normal
        hom3 = self.enemyPositions[3] # AISetting_Normal
        hom4 = self.enemyPositions[4] # AISetting_Normal
        hom5 = self.enemyPositions[5] # AISetting_Normal -> AISetting_Normal -> AISetting_Support
        hom6 = self.enemyPositions[6] # AISetting_HOM -> AISetting_Normal -> AISetting_Support
        bok1 = self.enemyPositions[7] # AISetting_SWD
        bok2 = self.enemyPositions[8] # AISetting_SWD
        rid1 = self.enemyPositions[9] # AISetting_RID -> AISetting_Normal -> AISetting_Support
        rid2 = self.enemyPositions[10] # AISetting_RID -> AISetting_Normal -> AISetting_Support
        bok3 = self.enemyPositions[11] # AISetting_BOK1 -> AISetting_BOK2
        bok4 = self.enemyPositions[12] # AISetting_BOK1 -> AISetting_BOK2
        bok5 = self.enemyPositions[13] # AISetting_BOK1 -> AISetting_BOK2 -> AISetting_Support
        rod1 = self.enemyPositions[14] # AISetting_Support
        assert len(self.enemyPositions) == 15

        self.heirophant = heirophant
        self.rod1 = rod1
        # self.boss = [
        #     heirophant, rod1,
        # ]

        self.enemiesHom = [
            hom1, hom2, hom3, hom4, hom5, hom6,
        ]

        self.enemiesBok = [
            bok3, bok4, bok5,
        ]

        self.enemiesAnywhere = [
            bok1, bok2, rid1, rid2,
        ]

        # CHANGE: set AISettingSwd -> AISetting_Support
        self.aiBoss0 = 59
        self.aiBoss1 = 62
        self.aiBoss2 = 63
        self.aiBoss3 = 57
        self.aiBok1 = 60
        self.aiHom = 61


        
    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Change AI of swd enemies
        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[11].getArg(1) == 'BOK1'
        funcs[11].setArg(2, 'AISetting_Normal')
        assert funcs[12].getArg(1) == 'BOK2'
        funcs[12].setArg(2, 'AISetting_Normal')

        # PC Positions
        while True:
            edgePt = self.mapGrid.randomEdgePoint()
            if edgePt:
                break

        points = set()
        candidates = sorted(vacant)
        count = 0
        while len(points) < 12:
            d = random.randint(0, 3)
            n = random.randint(2, 8)
            pt = self.mapGrid.randomNearbyPoint(edgePt, d, candidates, tol=count//10)
            count += 1
            if pt is None:
                continue
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Boss group
        bossPt = self.mapGrid.greatestDistance(edgePt)
        d = random.randint(0, 3)
        candidates = sorted(vacant)
        count = 0
        while True:
            bossPt0 = self.mapGrid.randomNearbyPoint(bossPt, d, candidates, tol=count//10)
            count += 1
            if bossPt0:
                break
        count = 0
        while True:
            bossPt2 = self.mapGrid.randomNearbyPoint(bossPt0, 3, candidates, tol=count//10)
            count += 1
            if bossPt2:
                break
        count = 0
        while True:
            rodPt = self.mapGrid.randomNearbyPoint(bossPt0, 1, candidates, tol=count//10)
            count += 1
            if rodPt:
                break
        self.setAIMoveGrid(self.aiBoss0, [bossPt0])
        self.setAIMoveGrid(self.aiBoss1, [bossPt0, bossPt2])
        self.setAIMoveGrid(self.aiBoss2, [bossPt2])
        self.setAIMoveGrid(self.aiBoss3, self.mapGrid.getValid())

        self.rod1.X, self.rod1.Y = rodPt
        self.heirophant.X, self.heirophant.Y = bossPt0

        vacant.remove(bossPt0)
        vacant.remove(rodPt)

        # BOK
        grid = self.mapGrid.bfs(bossPt0, 30, vacant)
        outline = self.mapGrid.outlineGrid(grid, vacant, length=4)
        points = random.sample(grid, len(self.enemiesBok))
        self.setPositions(points, self.enemiesBok)
        self.setAIMoveGrid(self.aiBok1, outline)

        vacant = vacant.difference(grid)
        vacant = vacant.difference(outline)

        # HOMs
        points = set()
        candidates = sorted(vacant)
        while len(points) < 50:
            x = random.randint(6, 16)
            y = random.randint(6, 16)
            rect = self.mapGrid.randomRectangle((x, y), 30, candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesHom)
        vacant = vacant.difference(points)
        self.setAIMoveGrid(self.aiHom, grid)

        # Remaining enemies
        points = set()
        candidates = sorted(vacant)
        while len(points) < len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(1, 10)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesAnywhere)

        self.setPCDirections()
        self.setEnemyDirections()

class MS19R_X44_P1(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms19r_x44_battle_01', 0, 'ms19r_x44_battle_S_01')

        self.exharme = self.enemyPositions.pop(0)
        gustadolph = self.enemyPositions[0] # AI_BOSS -> AI_BOSS0 (DefeatCount 1 / EV_TOWER) -> AI_BOSS1 (EV_KEIKAI)
        bow1 = self.enemyPositions[1] # DEF -> AI_TOWER (EV_TOWER) -> AI_BOSS1 (EV_KEIKAI)
        rod1 = self.enemyPositions[2] # DEF -> AI_BOSS1 (EV_KEIKAI)
        sld1 = self.enemyPositions[3] # DEF
        swd1 = self.enemyPositions[4] # DEF -> AI_ATKR (EV_ATKR)
        swd2 = self.enemyPositions[5] # DEF
        bok1 = self.enemyPositions[6] # DEF -> AI_ATKR (EV_ATKR) -> AI_TOWER (EV_TOWER)
        bok2 = self.enemyPositions[7] # DEF
        sld2 = self.enemyPositions[8] # AI_SLDB -> AI_CENTER (DefeatCount 1)
        swd3 = self.enemyPositions[9] # AI_CENTER -> AI_ATKL (EV_ATKL)
        bok3 = self.enemyPositions[10] # AI_CENTER -> AI_ATKL (EV_ATKL)
        sld3 = self.enemyPositions[11] # AI_CENTER
        sld4 = self.enemyPositions[12] # AI_CENTER
        rid1 = self.enemyPositions[13] # AI_BIRD -> FREE (DefeatCount 4) -> AI_TOWER (EV_TOWER) -> AI_BOSS1 (EV_KEIKAI)
        rid2 = self.enemyPositions[14] # AI_BIRD -> FREE (DefeatCount 4) -> AI_TOWER (EV_TOWER) -> AI_BOSS1 (EV_KEIKAI)
        rbw1 = self.enemyPositions[15] # AI_CBOW -> AI_BOSS1 (EV_KEIKAI)
        assert len(self.enemyPositions) == 16

        self.boss = [
            gustadolph
        ]

        self.birds = [
            rid1, rid2,
        ]

        self.birdArrow = [
            rbw1,
        ]

        self.enemiesDef = [
            bow1, rod1, sld1, swd1, swd2, bok1, bok2,
        ]

        self.enemiesCenter = [
            sld2, swd3, bok3, sld3, sld4,
        ]

        self.aiDef = 68
        self.aiBoss0 = 70
        self.aiCBow = 71
        self.aiSLDB = 72
        self.aiBird = 73
        self.aiTower = 74
        self.aiBoss = 79
        self.aiBoss1 = 80
        self.aiCenter = 82
        self.aiAtkL = 83


    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 20))

        inaccessibleRoofs = [
            (1, 13), (1, 14), (1, 15),
            (5, 11), (6, 11), (7, 11),
            (25, 9), (26, 9), (27, 9),
        ]

        accessibleRoofs = [
            (13, 13), (13, 14), (13, 15),
            (6, 5), (8, 5), (9, 5), (11, 5),
            (25, 15), (25, 16), (25, 17),
            (5, 20), (5, 21), (5, 22),
        ]

        vacant = vacant.difference(inaccessibleRoofs)

        # Get/Set AI Grids
        aiBird = inaccessibleRoofs + accessibleRoofs
        aiCBow = list(aiBird)
        self.setAIMoveGrid(self.aiBird, aiBird)
        self.setAIMoveGrid(self.aiCBow, aiCBow)

        aiCenter = self.getAIMoveGrid(self.aiCenter)
        aiAtkL = list(aiCenter)
        evAtkL = list(aiCenter)
        self.setAIMoveGrid(self.aiAtkL, aiAtkL)
        self.mapGrid.clearSpecs('EV_ATKL')
        self.mapGrid.addSpec('EV_ATKL', evAtkL)

        candidates = sorted(vacant)
        pt = random.sample(candidates, 1)[0]
        aiBoss1 = self.mapGrid.randomRectangle(pt, 110, candidates)
        self.setAIMoveGrid(self.aiBoss1, aiBoss1)

        candidates = sorted(vacant)
        boss0Cand = [
            (5, 21), (6, 16), (10, 5), (13, 21), (15, 15), (25, 16), (21, 7),
        ]
        boss0Point = random.sample(boss0Cand, 1)[0]
        aiBoss0 = self.mapGrid.bfs(boss0Point, 4, candidates)
        evKeiKai = self.mapGrid.bfs(boss0Point, 100, candidates)
        aiTower = self.mapGrid.bfs(boss0Point, 12, candidates)
        evTower = self.mapGrid.bfs(boss0Point, 8, candidates) # Just keep the same as aiTower????
        self.setAIMoveGrid(self.aiBoss0 ,aiBoss0)
        self.setAIMoveGrid(self.aiTower, aiTower)
        self.mapGrid.clearSpecs('EV_KEIKAI')
        self.mapGrid.addSpec('EV_KEIKAI', evKeiKai)
        self.mapGrid.clearSpecs('EV_TOWER')
        self.mapGrid.addSpec('EV_TOWER', evTower)

        # Set DEF & AI_BOSS
        candidates = sorted(vacant)
        count = 0
        while True:
            d = random.randint(15, 40)
            pt = self.mapGrid.randomNearbyPoint(boss0Point, d, candidates, tol=count//10)
            count += 1
            if pt is None:
                continue
            if self.mapGrid.shortestPath(boss0Point, pt): # Make sure points can be reached
                break
        aiDef = self.mapGrid.bfs(pt, 140, candidates)
        aiBoss = random.sample(aiDef, 1)
        self.setAIMoveGrid(self.aiDef, aiDef)
        assert len(self.boss) == 1
        self.setAIMoveGrid(self.aiBoss, aiBoss)
        
        candidates = sorted(vacant.intersection(aiBoss))
        self.setPositions(candidates, self.boss)
        vacant = vacant.difference(aiBoss)

        # Change AI settings as needed
        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[8].getArg(2) == 'AI_SLDB', funcs[8].getArg(2)
        funcs[8].setArg(2, 'AI_CENTER')

        funcs = self.battle.getLocalFunction('ChangeAISettings')[1]
        assert funcs[1].getArg(1) == 'SLD2', funcs[1].getArg(1)
        assert funcs[1].getArg(2) == 'AI_CENTER', funcs[1].getArg(2)
        funcs[1].setArg(1, 'RBW1')
        funcs[1].setArg(2, 'AI_BOSS0')
        
        funcs = self.battle.getLocalFunction('ChangeAISettings')[3]
        assert funcs[0].getArg(2) == 'AI_ATKR', funcs[0].getArg(2)
        assert funcs[1].getArg(2) == 'AI_ATKR', funcs[1].getArg(2)
        funcs[0].setArg(2, 'AI_CENTER')
        funcs[1].setArg(2, 'AI_CENTER')
        
        # Startings points for enemies
        candidates = sorted(vacant.intersection(aiBird))
        points = random.sample(candidates, len(self.birds))
        self.setPositions(points, self.birds)
        vacant = vacant.difference(points)

        candidates = sorted(vacant.intersection(aiCBow))
        points = random.sample(candidates, len(self.birdArrow))
        self.setPositions(points, self.birdArrow)
        vacant = vacant.difference(points)

        candidates = sorted(vacant.intersection(aiDef))
        points = set()
        while len(points) < 4*len(self.enemiesDef):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, len(self.enemiesDef))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesDef)
        vacant = vacant.difference(points)
    
        candidates = sorted(vacant.intersection(aiCenter))
        points = set()
        while len(points) < 4*len(self.enemiesCenter):
            pt = random.sample(candidates, 1)[0]
            n = random.randint(2, len(self.enemiesCenter))
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesCenter)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Place PCs
        nmPts = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPts, vacant, length=2)
        vacant = vacant.difference(aiDef).difference(outline).difference(nmPts)

        candidates = sorted(vacant)
        points = set()
        count = 0
        while len(points) < 13:
            pt = self.mapGrid.greatestDistance(aiBoss[0], grid=candidates, tol=3 + count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(2, 10)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 18:
                points = set()
            count += 1
        self.setPlayerPositions(points, ally=self.exharme)

        self.setPCDirections(allies=self.exharme)
        self.setEnemyDirections()

class MS19R_X44_P2(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms19r_x44_battle_02', 0, 'ms19r_x44_battle_S_02')

        svarog = self.enemyPositions[0] # AI_BOSS -> AI_BASE
        swd1 = self.enemyPositions[1] # AI_BASE
        swd2 = self.enemyPositions[2] # AI_BASE
        swd3 = self.enemyPositions[3] # AI_BASE
        swd4 = self.enemyPositions[4] # AI_BASE
        spr1 = self.enemyPositions[5] # AI_BASE
        spr2 = self.enemyPositions[6] # AI_BASE
        spr3 = self.enemyPositions[7]
        spr4 = self.enemyPositions[8]
        bow1 = self.enemyPositions[9] # AI_BASE
        bow2 = self.enemyPositions[10] # AI_BASE
        bok1 = self.enemyPositions[11] # AI_BASE
        bok2 = self.enemyPositions[12]
        rod1 = self.enemyPositions[13] # AI_BASE
        rod2 = self.enemyPositions[14]
        assert len(self.enemyPositions) == 15

        self.boss = [
            svarog, rod1,
        ]

        self.enemiesAnywhere = [
            swd1, swd2, swd3, swd4,
            spr1, spr2, spr3, spr4,
            bow1, bow2,
            bok1, bok2,
            rod2,
        ]

        self.aiBossMov = 20
        self.aiBossAtk = 16

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 24))

        # Allow boss to attack everywhere
        nx = self.mapGrid.nx
        ny = self.mapGrid.ny
        bossAtk = [(i,j) for i in range(nx) for j in range(ny)]
        self.setAIAtkGrid(self.aiBossAtk, bossAtk)

        # Pick some enemies to stay near the boss
        bossEnemies = list(self.boss)
        n = random.randint(2, len(self.enemiesAnywhere)//2)
        bossEnemies += random.sample(self.enemiesAnywhere, n)
        enemiesAnywhere = list(filter(lambda x: x not in bossEnemies, self.enemiesAnywhere))

        # Place boss enemies
        bossPts = set()
        candidates = sorted(vacant)
        n = 4*len(bossEnemies)
        while True:
            bossPt = random.sample(candidates, 1)[0]
            bossPts = self.mapGrid.randomRectangle(bossPt, n, candidates)
            if len(bossPts) >= n:
                break
        self.setPositions(bossPts, bossEnemies)
        bossPtsOutline = self.mapGrid.outlineGrid(bossPts, candidates, length=2)

        # Initial boss ai points
        candidates = sorted(vacant)
        attempts = 0
        while True:
            d = random.randint(4, 10)
            n = random.randint(3, 6)
            aiBoss = self.mapGrid.nearbyCluster(bossPt, d, n, candidates)
            if aiBoss and len(aiBoss) > 2:
                break
            attempts += 1
            if aiBoss and attempts >= 100:
                break
        self.setAIMoveGrid(self.aiBossMov, aiBoss)
        outline = self.mapGrid.outlineGrid(aiBoss, candidates, length=1)
        vacant = vacant.difference(aiBoss).difference(outline)
        vacant = vacant.difference(bossPts).difference(bossPtsOutline)

        # Place remaining enemies
        points = set()
        candidates = sorted(vacant)
        x = len(enemiesAnywhere)
        while len(points) < 4*x:
            n = random.randint(2*x, 3*x)
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
        self.setPositions(points, enemiesAnywhere)
        outline = self.mapGrid.outlineGrid(points, candidates, length=1)
        vacant = vacant.difference(points).difference(outline)

        # Place PCs
        nmPos = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPos, vacant, length=1)
        vacant = vacant.difference(outline).difference(nmPos)
        candidates = sorted(vacant)
        attempts = 0
        points = set()
        while True:
            pt = random.sample(candidates, 1)[0]
            # Keep PCs nearby as much as possible
            for count in range(100):
                d = random.randint(0, 10 + attempts)
                n = random.randint(2, 8)
                cluster = self.mapGrid.nearbyCluster(pt, d, n, candidates, tol=count//10)
                if cluster is None:
                    continue
                points.update(cluster)
                if len(points) >= 12:
                    break
            if len(points) > 22:
                points = set()
            if len(points) >= 12:
                break
            attempts += 1
        self.setPlayerPositions(points)        

        self.setPCDirections()
        self.setEnemyDirections()

class MS19F_X45_P1(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms19f_x45_battle_01', 1, 'ms19f_x45_battle_S_01')

        kamsell = self.enemyPositions[0] # AISetting4 -> AISetting2 (START ON BRIDGE, PAVEMENT, or FLATLAND)
        dag1 = self.enemyPositions[1]
        dag2 = self.enemyPositions[2] # AISetting3
        bow1 = self.enemyPositions[3]
        bok1 = self.enemyPositions[4] # AISetting3
        bok3 = self.enemyPositions[5]
        sld1 = self.enemyPositions[6]
        dag3 = self.enemyPositions[7]
        dag4 = self.enemyPositions[8] # AISetting3
        bow3 = self.enemyPositions[9]
        bok2 = self.enemyPositions[10]
        bow4 = self.enemyPositions[11]
        sld2 = self.enemyPositions[12]
        assert len(self.enemyPositions) == 13

        self.boss = [
            kamsell, bok2, bow4, dag3,
        ]

        self.enemiesAnywhere = [
            dag1, dag2, bow1, bok1, bok3,
            sld1, dag4, bow3, bow4, sld2,
        ]

        self.aiSetting4 = 22

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Setup spawned enemies
        pt1 = self.mapGrid.randomEdgePoint()
        zouenGroup1 = self.mapGrid.bfs(pt1, 3, vacant)
        while True:
            pt2 = self.mapGrid.randomEdgePoint()
            zouenGroup2 = self.mapGrid.bfs(pt2, 3, vacant)
            if set(zouenGroup1).intersection(zouenGroup2) == set():
                break

        zouenDefault = self.mapGrid.getIdxs('Zouen01')
        self.mapGrid.clearSpecs('Zouen01')
        self.mapGrid.addSpec('Zouen01', zouenGroup1 + zouenGroup2)
        func = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        self.setWaki(func[0], pt1)
        self.setWaki(func[1], pt2)

        # Place PCs
        points = set()
        candidates = sorted(vacant)
        while len(points) < 12:
            n = random.randint(2, 12)
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            points.update(rect)
            if len(points) > 20:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)
        pcRef = self.mapGrid.clusterMean(points)

        # Place boss group (maybe only on non-brine tiles?)
        while True:
            pt = self.mapGrid.greatestDistance(pcRef, grid=vacant, tol=5)
            grid = self.mapGrid.randomRectangle(pt, 20, vacant, d=10)
            if len(grid) > 2*len(self.boss):
                break
        self.setAIMoveGrid(self.aiSetting4, grid)
        self.setPositions(grid, self.boss)
        vacant = vacant.difference(grid)

        # Remaining enemies
        self.setPositions(vacant, self.enemiesAnywhere)

        self.setPCDirections()
        self.setEnemyDirections()

class MS19F_X45_P2(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms19f_x45_battle_02', 1, 'ms19f_x45_battle_S_02')

        his1 = self.enemyPositions.pop(0)
        his2 = self.enemyPositions.pop(0)
        his3 = self.enemyPositions.pop(0)
        idore = self.enemyPositions[0] # AISetting2 -> AIBoss
        sld1 = self.enemyPositions[1]
        dag2 = self.enemyPositions[2]
        sld2 = self.enemyPositions[3]
        dag3 = self.enemyPositions[4]
        spr1 = self.enemyPositions[5]
        rod1 = self.enemyPositions[6]
        rod2 = self.enemyPositions[7]
        spr4 = self.enemyPositions[8]
        bow2 = self.enemyPositions[9] # AISetting3
        bow3 = self.enemyPositions[10] # AISetting3
        rid1 = self.enemyPositions[11] # AISetting3
        rid2 = self.enemyPositions[12] # AISetting3
        rid3 = self.enemyPositions[13] # AISetting3
        assert len(self.enemyPositions) == 14

        self.his = [
            his1, his2, his3,
        ]

        self.boss = [
            idore, sld1, dag2, sld2, dag3, spr1,
            rod1, rod2, spr4,
        ]

        self.enemiesAnywhere = [
            rid1, rid2, rid3, bow2, bow3,
        ]

        self.aiEscape = 40
        self.aiSetting2 = 41
        self.aiSetting3 = 42
        self.aiSetting4 = 43
        self.aiSetting5 = 44
        self.aiBoss = 45
        self.aiHealerMov = 48
        self.aiHealerAtk = 39

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(0, 13))

        # Don't bother with AI_Escape2
        funcs = self.battle.getLocalFunction('ChangeAISettings')[0]
        assert funcs[8].getArg(2) == "AI_Escape2", funcs[8].getArg(2)
        funcs[8].setArg(2, "AI_Escape")

        # Path for setting up AI
        loop = []
        for i in range(0, 31):
            loop.append((i, 3))
        for j in range(4, 15):
            loop.append((30, j))
        for i in range(30, -1, -1):
            loop.append((i, 14))
        for j in range(14, 3, -1):
            loop.append((0, j))

        # Where to start loop -- where boss et al start
        l0 = random.randint(0, len(loop)-1)
        dl = random.sample([-1, 1], 1)[0] # "Clockwise" or "Counterclockwise"

        def getLoopPoint(i, offset=None):
            if offset is None:
                offset = 0
            j = (l0 + dl*offset + dl*i) % len(loop)
            pt = loop[j]
            if not self.mapGrid.isValid(*pt):
                length = 1
                outline = self.mapGrid.outlineGrid([pt], vacant, length=length)
                while not outline:
                    length += 1
                    outline = self.mapGrid.outlineGrid([pt], vacant, length=length)
                pt = random.sample(outline, 1)[0]
            return pt

        # Generate grids from the loop
        def loopToGrid(n, offset=None):
            if offset is None:
                offset = 0
            grid = []
            i = 0
            while len(grid) < n:
                grid.append(getLoopPoint(i, offset))
                i += 1
            outline = self.mapGrid.outlineGrid(grid, vacant, length=5)
            return sorted(set(grid + outline))

        aiBossGrid = loopToGrid(50, offset=15)
        aiSetting2Grid = loopToGrid(12)
        aiSetting3Grid = loopToGrid(65)
        aiSetting4Grid = loopToGrid(50)
        aiSetting5Grid = loopToGrid(8)

        self.setAIMoveGrid(self.aiBoss, aiBossGrid)
        self.setAIMoveGrid(self.aiSetting2, aiSetting2Grid)
        self.setAIMoveGrid(self.aiSetting3, aiSetting3Grid)
        self.setAIMoveGrid(self.aiSetting4, aiSetting4Grid)
        self.setAIMoveGrid(self.aiSetting5, aiSetting5Grid)

        # Set allok grid
        pt = getLoopPoint(20)
        allok = self.mapGrid.outlineGrid([pt], vacant, length=5)
        self.mapGrid.clearSpecs('ALLOK')
        self.mapGrid.addSpec('ALLOK', allok)
        
        goalPt = getLoopPoint(42)
        attempts = 0
        while attempts < 100:
            n = random.randint(4, 8)
            goalGrid = self.mapGrid.randomRectangle(goalPt, n, vacant)
            if len(goalGrid) >= 4:
                break
            attempts += 1
        self.mapGrid.clearSpecs('Goal')
        self.mapGrid.addSpec('Goal', goalGrid)
        self.setAIMoveGrid(self.aiEscape, goalGrid)        

        # HIS AI
        healAtkGrid = loopToGrid(30, offset=12) + goalGrid
        healMovGrid = loopToGrid(25, offset=17) + goalGrid
        self.setAIMoveGrid(self.aiHealerMov, healMovGrid)
        self.setAIAtkGrid(self.aiHealerAtk, healAtkGrid)

        # Place enemies
        grid = sorted(vacant.intersection(set(aiSetting3Grid).difference(aiSetting4Grid).union(goalGrid)))
        points = random.sample(grid, len(self.enemiesAnywhere))
        vacant = vacant.difference(points)
        self.setPositions(points, self.enemiesAnywhere)

        # Set boss enemies in AISetting5 grid
        points = set()
        candidates = sorted(vacant)
        while len(points) < len(self.boss):
            pt = random.sample(aiSetting5Grid, 1)[0]
            n = random.randint(2, len(self.boss))
            rect = self.mapGrid.randomRectangle(pt, n, candidates, d=6)
            points.update(rect)
        outline = self.mapGrid.outlineGrid(points, candidates, length=2)
        vacant = vacant.difference(points).difference(outline)
        self.setPositions(points, self.boss)

        # HIS start
        hisPoints = set()
        candidates = sorted(vacant)
        count = 0
        maxA = 15
        while len(hisPoints) < 3:
            a = random.randint(10 + count//10, 15 + count//10)
            lp = getLoopPoint(a)
            pt = self.mapGrid.randomNearbyPoint(lp, 0, candidates, dh=10)
            count += 1
            if pt is None:
                continue
            hisPoints.add(pt)
        self.setPositions(hisPoints, self.his)
        vacant = vacant.difference(hisPoints)

        # Ensure PCs aren't next to enemies
        nmPoints = [(e.X, e.Y) for e in self.enemyPositions]
        outline = self.mapGrid.outlineGrid(nmPoints, vacant, length=1)
        vacant = vacant.difference(outline)

        # PCs start
        pcPoints = set()
        candidates = sorted(vacant)
        count = 0
        while len(pcPoints) < 16:
            a = random.randint(8 + count//10, 15 + count//10)
            lp = getLoopPoint(a)
            d = random.randint(0, 3)
            pt = self.mapGrid.randomNearbyPoint(lp, d, candidates, dh=10)
            count += 1
            if pt is None:
                continue
            n = random.randint(4, 10)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            pcPoints.update(rect)
            if len(pcPoints) > 28:
                pcPoints = set()
        self.setPlayerPositions(pcPoints)
        vacant = vacant.difference(pcPoints)

        # Set wakis
        grid = sorted(set(aiSetting3Grid).union(aiSetting5Grid).difference(aiSetting4Grid))
        points = random.sample(grid, 3)
        funcs = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        for p, f in zip(points, funcs):
            self.setWaki(f, p)

        # Set camera for overview
        pt = self.mapGrid.clusterMean(goalGrid)
        func = self.battle.getLocalFunction('ChangeStageCameraToMapGrid')[0]
        func.setArg(1, float(pt[0]))
        func.setArg(1, float(pt[1]))

        self.setPCDirections(allies=self.his)
        self.setEnemyDirections()

class MS19S_X46(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms19s_x46_battle_01', 1, 'ms19s_x46_battle_S_01')

        kamsell = self.enemyPositions[0] # AISetting1 -> AISetting2
        slde2 = self.enemyPositions[1] # AISetting4
        dag1 = self.enemyPositions[2] # AISetting4
        bok3 = self.enemyPositions[3]
        dag2 = self.enemyPositions[4] # AISetting3
        dag4 = self.enemyPositions[5] # AISetting3
        bok1 = self.enemyPositions[6] # AISetting3
        slde1 = self.enemyPositions[7] # AISetting4
        bok2 = self.enemyPositions[8] # AISetting4
        dag3 = self.enemyPositions[9]
        rod2 = self.enemyPositions[10] # AISetting3
        assert len(self.enemyPositions) == 11

        self.boss = [
            kamsell, rod2, dag3, bok2, bok1, slde1,
        ]

        self.enemiesAnywhere = [
            slde2, dag1, bok3, dag2, dag4, 
        ]

        self.aiSetting1 = 19

    def updateEnforcedPCs(self, mapPCs):
        pass

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Setup spawned enemies
        pt = self.mapGrid.randomEdgePoint()
        zouenGroup = self.mapGrid.bfs(pt, 3, vacant)

        self.mapGrid.clearSpecs('Zouen02')
        self.mapGrid.addSpec('Zouen02', zouenGroup)
        func = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')[0]
        self.setWaki(func, pt)

        # Place PCs
        pcPoints = set()
        candidates = sorted(vacant)
        refPoint = random.sample(candidates, 1)[0]
        count = 0
        while len(pcPoints) < 12:
            d = random.randint(2, 5)
            pt = self.mapGrid.randomNearbyPoint(refPoint, d, candidates, dh=10, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(2, 12)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            pcPoints.update(rect)
            if len(pcPoints) > 20:
                pcPoints = set()
        self.setPlayerPositions(pcPoints)
        outline = self.mapGrid.outlineGrid(pcPoints, vacant, length=2)
        vacant = vacant.difference(pcPoints).difference(outline)
        ptPoint = self.mapGrid.clusterMean(pcPoints)

        # Pick a point for boss far away
        pt = self.mapGrid.greatestDistance(ptPoint, grid=vacant, tol=5)
        grid = self.mapGrid.bfs(pt, 20, vacant, d=3)
        self.setAIMoveGrid(self.aiSetting1, grid)
        self.setPositions(grid, self.boss)
        vacant = vacant.difference(grid)

        # Remaining enemies
        pt = self.mapGrid.greatestDistance(ptPoint, grid=vacant, tol=10)
        grid = self.mapGrid.bfs(pt, 30, vacant, d=10)
        self.setPositions(grid, self.enemiesAnywhere)
        vacant = vacant.difference(grid)

        self.setPCDirections()
        self.setEnemyDirections()

class MS20S_X47(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms20s_x47_battle_01', 1, 'ms20s_x47_battle_S_01')

        exharme = self.enemyPositions[0] # AISetting1 -> AISetting2
        hsld2 = self.enemyPositions[1]
        hsld1 = self.enemyPositions[2]
        hspr1 = self.enemyPositions[3]
        bow1 = self.enemyPositions[4]
        rod1 = self.enemyPositions[5] # AISetting1 -> AISetting2
        rid4 = self.enemyPositions[6]
        rid1 = self.enemyPositions[7]
        rid3 = self.enemyPositions[8]
        rid5 = self.enemyPositions[9]
        rid2 = self.enemyPositions[10]
        assert len(self.enemyPositions) == 11

        self.boss = [
            exharme, rod1,
        ]

        self.enemiesAnywhere = [
            hsld2, hsld1, hspr1, bow1, rid4, rid1, rid3, rid5, rid2,
        ]

        self.aiSettings1 = 11

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        # Pick group(s) for PCs
        candidates = sorted(vacant)
        points = set()
        while len(points) < 20:
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, 14, candidates)
            points.update(rect)
            if len(points) > 30:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=3)
        vacant = vacant.difference(points).difference(outline)
        
        # Spawn enemies
        pt1 = self.mapGrid.randomEdgePoint(grid=vacant)
        while True:
            pt2 = self.mapGrid.randomEdgePoint(grid=vacant)
            if self.mapGrid.distance(pt1, pt2) > 10:
                break
            
        zouenDefault = self.mapGrid.getIdxs('Zouen02')
        zouenNew = self.mapGrid.bfs(pt1, len(zouenDefault), vacant)
        self.mapGrid.clearSpecs('Zouen02')
        self.mapGrid.addSpec('Zouen02', zouenNew)

        zouenDefault = self.mapGrid.getIdxs('Zouen03')
        zouenNew = self.mapGrid.bfs(pt2, len(zouenDefault), vacant)
        self.mapGrid.clearSpecs('Zouen03')
        self.mapGrid.addSpec('Zouen03', zouenNew)

        funcs = self.battle.getLocalFunction('CreateGeneratePointOnMapEx')
        self.setWaki(funcs[0], pt1)
        self.setWaki(funcs[1], pt2)

        # Place boss in rectangle
        candidates = sorted(vacant)
        grid = self.getAIMoveGrid(self.aiSettings1)
        while True:
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.bfs(pt, len(grid), candidates)
            if len(rect) > len(self.boss):
                break
        self.setPositions(rect, self.boss)
        self.setAIMoveGrid(self.aiSettings1, rect)
        vacant = vacant.difference(rect)

        # Place remaining enemies
        candidates = sorted(vacant)
        points = set()
        while len(points) < 3*len(self.enemiesAnywhere):
            pt = random.sample(candidates, 1)[0]
            rect = self.mapGrid.randomRectangle(pt, len(self.enemiesAnywhere), candidates)
            points.update(rect)
        self.setPositions(points, self.enemiesAnywhere)        

        self.setPCDirections()
        self.setEnemyDirections()


class MS21S_X48_P1(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms21s_x48_battle_01', 1, 'ms21s_x48_battle_S_01')

        lyla = self.enemyPositions[0] # AI_BOSS -> AI_BOSS2 -> AI_BOSS3
        dag1 = self.enemyPositions[1] # AI_SUPPORT
        dag2 = self.enemyPositions[2] # AI_SUPPORT
        swd2 = self.enemyPositions[3] # AI_SUPPORT
        swd3 = self.enemyPositions[4] # AI_SUPPORT
        spr1 = self.enemyPositions[5] # AI_SUPPORT
        spr2 = self.enemyPositions[6] # AI_SUPPORT
        spr3 = self.enemyPositions[7] # AI_SUPPORT
        sld1 = self.enemyPositions[8] # AI_SUPPORT
        sld2 = self.enemyPositions[9] # AI_SUPPORT
        bow1 = self.enemyPositions[10] # AI_BOW -> AI_NORMAL
        bow2 = self.enemyPositions[11] # AI_BOW -> AI_NORMAL
        rod1 = self.enemyPositions[12] # AI_SUPPORT
        rod2 = self.enemyPositions[13] # AI_SUPPORT
        rod3 = self.enemyPositions[14] # AI_SUPPORT
        assert len(self.enemyPositions) == 15

        self.boss = [
            lyla, rod1, # Right next to Lyla
            rod2, rod3, # In front of Lyla & rod1
        ]

        self.enemiesAnywhere = [
            dag1, dag2, swd2, swd3,
            spr1, spr2, spr3,
            sld1, sld2,
        ]

        self.enemiesBow = [
            bow1, bow2,
        ]

        # Start in boss2, ensure boss is subset of boss2
        # boss3 is superset of boss2
        self.aiBoss1 = 31
        self.aiBoss2 = 36
        self.aiBoss3 = 37 # Keep this the same; almost everywhere already!

        self.aiBow = 33
        

    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(10, 10))

        gridBoss1 = self.getAIMoveGrid(self.aiBoss1)
        gridBoss2 = self.getAIMoveGrid(self.aiBoss2)
        gridBoss3 = self.getAIMoveGrid(self.aiBoss3)
        gridBow = self.getAIMoveGrid(self.aiBow)

        # Filter grid
        gridBoss1 = list(filter(lambda x: x[0] < 20, gridBoss1))

        # New grids
        while True:
            newGridBoss1 = self.mapGrid.randomCluster(len(gridBoss1), gridBoss3)
            if len(newGridBoss1) < 1.5*len(gridBoss1):
                break

        while True:
            newGridBoss2 = self.mapGrid.randomCluster(len(gridBoss2), gridBoss3)
            if len(newGridBoss2) < 1.5*len(gridBoss2):
                break

        self.setAIMoveGrid(self.aiBoss1, newGridBoss1)
        self.setAIMoveGrid(self.aiBoss2, newGridBoss2)

        outline = self.mapGrid.outlineGrid(newGridBoss1, vacant, length=1)
        grid = sorted(set(outline + newGridBoss1).intersection(gridBoss3))
        self.setPositions(grid, self.boss)
        outline = self.mapGrid.outlineGrid(grid, vacant, length=1)
        vacant = vacant.difference(grid).difference(outline)
        bossPt = self.mapGrid.clusterMean(grid)

        # Bow
        candidates = set(vacant).intersection(gridBow)
        length = 1
        assert len(candidates) > 2*len(self.enemiesBow), len(candidates)
        while len(candidates) < 2*len(self.enemiesBow):
            outline = self.mapGrid.outlineGrid(candidates, vacant, length)
            candidates.update(outline)
            length += 1
        candidates = sorted(candidates)
        pts = random.sample(candidates, len(self.enemiesBow))
        self.setPositions(pts, self.enemiesBow)
        outline = self.mapGrid.outlineGrid(pts, vacant, length=1)
        vacant = vacant.difference(pts).difference(outline)

        # Place PCs
        pcPoints = set()
        candidates = sorted(vacant)
        refPoint = self.mapGrid.greatestDistance(bossPt, grid=vacant, tol=2)
        count = 0
        while len(pcPoints) < 11:
            d = random.randint(1, 3)
            pt = self.mapGrid.randomNearbyPoint(refPoint, d, candidates, dh=10, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(3, 10)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            pcPoints.update(rect)
            if len(pcPoints) > 18:
                pcPoints = set()
        self.setPlayerPositions(pcPoints)
        outline = self.mapGrid.outlineGrid(pcPoints, vacant, length=2)
        vacant = vacant.difference(pcPoints).difference(outline)

        # Remaining enemies anywhere in gridBoss3
        candidates = set(vacant).intersection(gridBoss3)
        length = 1
        while len(candidates) < 3*len(self.enemiesAnywhere):
            outline = self.mapGrid.outlineGrid(candidates, vacant, length)
            candidates.update(outline)
            length += 1
        candidates = sorted(candidates)
        self.setPositions(candidates, self.enemiesAnywhere)

        self.setPCDirections()
        self.setEnemyDirections()


class MS21S_X48_P2(Level):
    def __init__(self, pak):
        super().__init__(pak, 'ms21s_x48_battle_02', 1, 'ms21s_x48_battle_S_02')

        self.idore = self.enemyPositions[0]
        heirophant = self.enemyPositions[1]
        hom1 = self.enemyPositions[2]
        hom7 = self.enemyPositions[3]
        hom2 = self.enemyPositions[4]
        hom3 = self.enemyPositions[5]
        hom4 = self.enemyPositions[6]
        hom5 = self.enemyPositions[7]
        hom8 = self.enemyPositions[8]
        hom9 = self.enemyPositions[9]
        hom10 = self.enemyPositions[10]
        hom11 = self.enemyPositions[11]
        assert len(self.enemyPositions) == 12

        self.boss = [
            self.idore
        ]

        self.enemiesAnywhere = [
            heirophant,
            hom1, hom7, hom2, hom3,
            hom4, hom5, hom8, hom9,
            hom10, hom11,
        ]

        self.aiBoss1 = 20
        self.aiBoss2 = 21


    def random(self):
        self.isRandomized = True
        vacant = set(self.mapGrid.getAccessible(13, 13))

        # Set Idore's grid and starting point
        while True:
            X, Y = random.sample(vacant, 1)[0]
            grid = [(X+i, Y+j) for i in range(-3, 3) for j in range(-3, 4)]
            boss1 = sorted(vacant.intersection(grid))
            if len(boss1) >= 35:
                break
        self.setAIMoveGrid(self.aiBoss1, boss1)
        bossPt = self.mapGrid.clusterMean(boss1)
        self.idore.X, self.idore.Y = bossPt
        boss1 += self.mapGrid.outlineGrid(boss1, vacant, length=4)
        vacant.remove(bossPt)
        
        # Pick points for PCs
        points = set()
        candidates = sorted(vacant.difference(boss1))
        refPoint = self.mapGrid.greatestDistance(bossPt, grid=vacant, tol=2)
        count = 0
        while len(points) < 11:
            d = random.randint(2, 5)
            pt = self.mapGrid.randomNearbyPoint(refPoint, d, vacant, dh=10, tol=count//10)
            count += 1
            if pt is None:
                continue
            n = random.randint(3, 8)
            rect = self.mapGrid.randomRectangle(pt, n, candidates)
            pattern = sorted(rect)[::2]
            points.update(pattern)
            if len(points) > 18:
                points = set()
        self.setPlayerPositions(points)
        outline = self.mapGrid.outlineGrid(points, vacant, length=2)
        vacant = vacant.difference(points).difference(outline)

        # Set Boss2 grid
        if bossPt[1] <= 8 or bossPt[1] >= 18:
            boss2 = [(i, j) for i in range(0, 27) for j in range(6, 21)]
            self.setAIMoveGrid(self.aiBoss2, boss2)
        elif bossPt[0] >= 17:
            boss2 = [(i, j) for i in range(10, 21) for j in range(0, 27)]
            self.setAIMoveGrid(self.aiBoss2, boss2)
        else:
            boss2 = self.getAIMoveGrid(self.aiBoss2)

        # Pick enemy points from boss2
        candidates = sorted(vacant.intersection(boss2))
        self.setPositions(candidates, self.enemiesAnywhere)
        vacant = vacant.difference(points).difference(boss2)

        self.setPCDirections()
        self.setEnemyDirections()


def initLevels(pak):
    levels = [
        MS01_X01(pak), # Beset by Brigands
        MS02_X02(pak), # The Tourney
        MS03_X03(pak), # Subduing the Smugglers
        MS03_X04(pak), # Apprehending the Rebels
        MS04_X05(pak), # Defending Dragan
        MS05_X06(pak), # Storming the Whiteholm Castle Gardens
        MS06_X07(pak), # Escape from Whiteholm Castle
        MS07_X08(pak), # General Avlora's Assault
        MS07_X09(pak), # Landroi's Last Stand
        MS08A_X10(pak), # Betrayal Beneath the Tellioran Moon
        MS08A_X11(pak), # House Telliore's Treachery
        MS08B_X12(pak), # House Ende's Assault
        MS08B_X13(pak), # Attack on Avlora
        MS09_X14(pak), # A Rematch with Bandits
        MS09_X15(pak), # The Battle of Booker's Brigade
        MS10A_X16(pak), # Clash with Sycras
        MS10A_X17(pak), # A Battle with the Herosbane
        MS10B_X18(pak), # The Battle of House Ende
        MS10B_X19(pak), # A Decisive Duel
        MS11_X20(pak), # Routing the Roselle
        MS11_X21(pak), # Safeguarding the Roselle
        MS12_X22(pak), # Confronting Silvio
        MS13_X24(pak), # Securing Telliore Reservoir
        MS13_X25(pak), # Securing the Warship
        MS13_X26(pak), # Securing Whiteholm Bridge
        MS14_X27(pak), # Battle Upon the Bridge
        MS14_X28(pak), # Clash Within Whiteholm Castle
        MS14_X29(pak), # Skirmish on the Norzelia River
        MS15_X30(pak), # Patriatte's Gambit
        MS15_X31_P1(pak), # Routing the Royalists
        MS15_X31_P2(pak), # Routing the Royalists
        MS15_X32(pak), # Battle with the Bandit Travis
        MS15_X33(pak), # Battle with the Bandit Trish
        MS16_X34(pak), # Eliminating the Aesfrosti Soldiers
        MS17S_X38(pak), # Benedict's Battle
        MS18B_X39(pak), # Confronting Clarus
        MS18R_X40(pak), # Battle of Twinsgate
        MS18F_X41(pak), # Battle at the Ministry
        MS18S_X42(pak), # Roland's Battle
        MS19B_X43_P1(pak), # The End of Exharme
        MS19B_X43_P2(pak), # The Holy Automaton
        MS19R_X44_P1(pak), # Defeating the Archduke
        MS19R_X44_P2(pak), # Battling the Embittered Svarog
        MS19F_X45_P1(pak), # Flight From the Source
        MS19F_X45_P2(pak), # Fighting Idore the Deluded
        MS19S_X46(pak), # Frederica's Battle
        MS20S_X47(pak), # Piercing the Goddess's Shield
        MS21S_X48_P1(pak), # Fighting Lyla Viscraft
        MS21S_X48_P2(pak), # The Final Battle
    ]

    return levels


def randomizeLevelInits(levels, seed, test=False):
    # If an undiscovered bug happens, just reinitialize and try again on a different seed.
    # High time just as safety net for slow computers.
    # The ENTIRE for loop is doable in <1 second in my testing.
    for i, level in enumerate(levels):
        n = 0
        while True:
            n += 1
            random.seed(seed+i+n)
            if test:
                signal.signal(signal.SIGALRM, level.random)
                signal.alarm(10)
            try:
                level.random()
                level.checkAllEnemiesMoved()
                print(level.__class__.__name__, 'passed')
            except Exception as e:
                print(level.__class__.__name__, e)
                level.__init__(pak)
                if test: raise Exception('Failed')
            else:
                break

    if test:
        assert i == len(levels), f"Failed on {level.__class__.__name__}"
