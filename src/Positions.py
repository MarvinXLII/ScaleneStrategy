import random
from Lub import Lub
import hjson
import os
from Assets import UAsset
from Utility import Byte, File
from copy import deepcopy

class POSITION:
    def __init__(self, func, mapGrid, x_index, y_index, dir_index):
        self.func = func
        self.mapGrid = mapGrid
        self.x_index = x_index
        self.y_index = y_index
        self.dir_index = dir_index
        self.moved = False
        try:
            self.specs = set(self.mapGrid.getSpec(self.X, self.Y))
        except:
            assert self.X < 0 or self.Y < 0
            X = max(self.X, 0)
            Y = max(self.Y, 0)
            self.specs = set(self.mapGrid.getSpec(X, Y))

    def wontMove(self):
        self.moved = True

    @property
    def X(self):
        return int(self.func.getArg(self.x_index))

    @X.setter
    def X(self, x):
        self.moved = True
        self.func.setArg(self.x_index, float(x))

    @property
    def Y(self):
        return int(self.func.getArg(self.y_index))

    @Y.setter
    def Y(self, y):
        self.moved = True
        self.func.setArg(self.y_index, float(y))


class PLAYERPOSITION(POSITION):
    def __init__(self, func, mapGrid, x_index=1, y_index=2, dir_index=3):
        super().__init__(func, mapGrid, x_index, y_index, dir_index)

    @property
    def direction(self):
        return self.func.getArg(self.dir_index)

    @direction.setter
    def direction(self, direction):
        assert direction in ['NORTH','SOUTH','EAST','WEST']
        self.func.setArg(self.dir_index, f"CHAR_DIR_{direction}")

    def bestDirection(self, x, y):
        dx = x - self.X
        dy = y - self.Y
        if abs(dx) > abs(dy):
            if dx > 0:
                self.direction = "NORTH"
            else:
                self.direction = "SOUTH"
        else:
            if dy > 0:
                self.direction = "EAST"
            else:
                self.direction = "WEST"


class ENEMYPOSITION(PLAYERPOSITION):
    def __init__(self, func, mapGrid):
        super().__init__(func, mapGrid, 4, 5, 6)

    @property
    def name(self):
        return self.func.getArg(1)

    @name.setter
    def name(self, n):
        self.func.setArg(1, n)


class SPAWNPOSITION(PLAYERPOSITION):
    def __init__(self, func, mapGrid):
        super().__init__(func, mapGrid, 2, 3, 4)
