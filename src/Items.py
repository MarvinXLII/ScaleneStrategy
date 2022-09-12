from Assets import Data
import random
from copy import deepcopy
import hjson
import os

class Shops:
    def __init__(self, pak):
        self.gop = Data(pak, 'GOP_Shop_List.uasset')
        self.data = self.gop.getDataTable()

    def randomInventory(self):
        for key, item in self.data.items():
            n = []
            for i in range(1, 8):
                if item[f'StockAddFlag{i}'].string:
                    n.append(item[f'StockAddNum{i}'].value)
            if n == []:
                continue
            min_n = min(n)
            if item['UpgradeMaterialRecId'].name != 'None':
                x = 0.8 + 0.4 * random.random()  ## +/- 20%
            else:
                x = 0.4 + 1.2 * random.random()  ## +/- 60%
            for i in range(1, 8):
                if item[f'StockAddFlag{i}'].string:
                    v = int(n.pop(0) * x)
                    v = min(v, 99)
                    item[f'StockAddNum{i}'].value = v

    def update(self):
        self.gop.update()

class Costs:
    def __init__(self, pak, filename):
        self.gop = Data(pak, filename)
        self.data = self.gop.getDataTable()

    # Input a percent to increase/decrease
    def randomCost(self, percent):
        assert percent >= 1 and percent <= 100
        f = percent / 100
        for item in self.data.values():

            # Skip items that can't be bought
            b = item['BuyPrice'].value
            if b == 0:
                continue
            
            # Buying price
            nb = random.randint(b * (1-f), b * (1+f) + 1)
            if nb >= 1000:
                nb = (nb // 100) * 100
            else:
                nb = (nb // 10) * 10
            item['BuyPrice'].value = int(nb)

            # Skip items that can't be sold
            s = item['SellPrice'].value
            if s == -1:
                continue
            
            # Selling price
            r = float(s) / b
            ns = nb * r
            if ns >= 1000:
                ns = (ns // 100) * 100
            else:
                ns = (ns // 10) * 10
            item['SellPrice'].value = int(ns)

    def update(self):
        self.gop.update()


# Not much potential with this beyond costs
class Accessories(Costs):
    def __init__(self, pak):
        super().__init__(pak, 'GOP_Battle_Accessary.uasset')

class ClassMedal(Costs):
    def __init__(self, pak):
        super().__init__(pak, 'GOP_Item_ClassMedal.uasset')

class ItemBattle(Costs):
    def __init__(self, pak):
        super().__init__(pak, 'GOP_Item_Battle.uasset')

class UpgradeMaterial(Costs):
    def __init__(self, pak):
        super().__init__(pak, 'GOP_Item_UpgradeMaterial.uasset')


class ResearchItems:
    def __init__(self, pak, filename):
        self.gop = Data(pak, filename)
        self.dropItem = self.gop.getCommand('BP_NeweraDropItemPointActor_C')
        self.locations = {}
        for k, d in self.dropItem.items():
            idx = d['RootComponent'].value
            self.locations[k] = self.gop.getUExp1Obj(idx)

    def changeItem(self, objIdx, itemName, number):
        itemId, count = self.dropItem[objIdx]['DropItemIds'].array[0].values()
        self.gop.uasset.addIndex(itemName)
        itemId.name = itemName
        count.value = number

    def getLocation(self, objIdx):
        location = self.locations[objIdx]['RelativeLocation']
        return location.x, location.y, location.z

    def setLocation(self, objIdx, x, y, z):
        self.locations[objIdx]['RelativeLocation'].x = x
        self.locations[objIdx]['RelativeLocation'].y = y
        self.locations[objIdx]['RelativeLocation'].z = z

    def update(self):
        self.gop.update()


def research_item_modding_demo(pak):
    print('Research Item Modding Demo')

    research = ResearchItems(pak, 'A1_EX_Street_R_OTH_ms02_x02.umap')    

    research.changeItem(10, 'ITEM_BATTLE_MAGIC_FIRE', 10)
    research.changeItem(11, 'ITEM_CLASSMEDAL_HIGH', 4)
    research.changeItem(12, 'BATTLE_ACCESSARY_IMMORTAL_PLUME', 42)

    x, y, z = research.getLocation(12)
    research.setLocation(12, x+900.0, y+500.0, z-38.0*4)

    research.update()
