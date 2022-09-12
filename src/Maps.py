from Assets import Data
import random
from copy import deepcopy
import hjson
import os


# Should test weather indoors
class MapCfg:
    def __init__(self, pak):
        self.gop = Data(pak, 'GOP_Battle_MapCfg.uasset')
        self.data = self.gop.getDataTable()

    def setTimeHour(self, mapkey, hour):
        assert hour in [6, 8, 12, 18, 22, 24]
        self.data['iInitialTimeHour'].value = hour

    def listKeys(self):
        return list(filter(lambda x: 'TEST' not in x, self.data.keys()))

    def shuffleTimes(self):
        print('Shuffling times')
        keys = self.listKeys()
        for i, ki in enumerate(keys):
            kj = random.sample(keys[i:], 1)[0]
            self.data[ki]['iInitialTimeHour'], self.data[kj]['iInitialTimeHour'] = \
                self.data[kj]['iInitialTimeHour'], self.data[ki]['iInitialTimeHour']

    # Consider skipping "INDOOR" conditions in tact
    def shuffleWeather(self):
        print('Shuffling weather')
        keys = self.listKeys()
        for i, ki in enumerate(keys):
            kj = random.sample(keys[i:], 1)[0]
            self.data[ki]['InitialWeatherTableId'], self.data[kj]['InitialWeatherTableId'] = \
                self.data[kj]['InitialWeatherTableId'], self.data[ki]['InitialWeatherTableId']
            self.data[ki]['eInitialWeatherType'], self.data[kj]['eInitialWeatherType'] = \
                self.data[kj]['eInitialWeatherType'], self.data[ki]['eInitialWeatherType']

    # Consider skipping "INDOOR" conditions in tact
    def shuffleWind(self):
        print('Shuffling wind')
        keys = self.listKeys()
        for i, ki in enumerate(keys):
            kj = random.sample(keys[i:], 1)[0]
            self.data[ki]['InitialWindTableId'], self.data[kj]['InitialWindTableId'] = \
                self.data[kj]['InitialWindTableId'], self.data[ki]['InitialWindTableId']
            self.data[ki]['eInitialWindType'], self.data[kj]['eInitialWindType'] = \
                self.data[kj]['eInitialWindType'], self.data[ki]['eInitialWindType']

    def update(self):
        self.gop.update()
