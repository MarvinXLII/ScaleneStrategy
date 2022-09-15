from Assets import Data
import random
from copy import deepcopy
import hjson
import os
from Utility import get_filename
import math
import sys

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


class Place:
    def __init__(self, pak, filename, skip=None):
        self.gop = Data(pak, filename)
        self.filename = filename
        self.dropItem = self.gop.getCommand('BP_NeweraDropItemPointActor_C')
        if skip is None: skip = []
        self.itemIndices = list(filter(lambda x: x not in skip, self.dropItem.keys()))
        self.skip = skip

        # Relative locations, i.e. where each item is on the map
        # (Probably too much work to do anything with these!)
        self.relLoc = {}
        for itemIndex in self.itemIndices:
            d = self.dropItem[itemIndex]
            idx = d['RootComponent'].value
            self.relLoc[itemIndex] = self.gop.getUExp1Obj(idx)

    def getItemList(self):
        itemList = []
        for itemIndex in self.itemIndices:
            item = self.dropItem[itemIndex]['DropItemIds'].array[0]
            itemName = item['ItemId'].name
            itemCount = item['Count'].value
            itemList.append((itemIndex, itemName, itemCount))
        return itemList

    def setItem(self, itemIndex, itemName, number):
        assert itemIndex in self.itemIndices
        itemId, count = self.dropItem[itemIndex]['DropItemIds'].array[0].values()
        self.gop.uasset.addIndex(itemName)
        itemId.name = itemName
        if itemName == 'ITEM_MONEY':
            v = 100 * (number // 100)
            count.value = max(150, v)
        elif itemName[:4] == 'NOTE':
            assert number == 1
            count.value = number
        else:
            if number == 1:
                count.value = 0
            else:
                count.value = number

    def getRelativeLocation(self, itemIndex):
        assert itemIndex in self.itemIndices
        relLoc = self.relLoc[itemIndex]['RelativeRelativeLocation']
        return relLoc.x, relLoc.y, relLoc.z

    def setRelativeLocation(self, itemIndex, x, y, z):
        assert itemIndex in self.itemIndices
        self.relLoc[objIdx]['RelativeLocation'].x = x
        self.relLoc[objIdx]['RelativeLocation'].y = y
        self.relLoc[objIdx]['RelativeLocation'].z = z

    def update(self):
        self.gop.update()


class Chapter:
    buyPrice = hjson.load(open(get_filename('json/itemPrice.json'),'r'))
    itemList = set()
    
    def __init__(self, pak, chapterName, fileDict):
        self.pak = pak
        self.chapterName = chapterName
        self.fileDict = fileDict
        if not self.fileDict:
            self.places = None
            return
        if 'Skip' in self.fileDict:
            self.skip = self.fileDict['Skip']
        else:
            self.skip = None

        self.costMin = self.fileDict['Worth']['min']
        self.costMax = self.fileDict['Worth']['max']

        self.places = {}
        for place, filename in self.fileDict['Places'].items():
            assert place not in self.places
            self.places[place] = []
            for fi in filename:
                if self.skip and fi in self.skip:
                    placeData = Place(pak, fi, skip=self.skip[fi])
                else:
                    placeData = Place(pak, fi)
                self.places[place].append(placeData)
            for p in self.places[place]:
                for _, item, _ in p.getItemList():
                    Chapter.itemList.add(item)

    # Get min and max cost of items
    def getCostBounds(self):
        costMin = 1e9
        costMax = 0
        for placeList in self.places.values():
            for place in placeList:
                itemList = place.getItemList()
                for _, item, count in itemList:
                    if item == 'ITEM_MONEY':
                        # costMin = min(costMin, count)
                        # costMax = max(costMax, count)
                        continue
                    if item not in Chapter.itemList:
                        continue
                    if item[:4] == 'NOTE':
                        continue # Ignore these costs; items will be overwritten
                    count = max(1, count)
                    price = Chapter.buyPrice[item]
                    costMin = min(costMin, price*count)
                    costMax = max(costMax, price*count)
        costMin = int(costMin * 0.5)
        costMax = int(costMax * 1.5)
        return costMin, costMax

    def randomItems(self):
        if not self.places:
            return

        ### DON'T DELETE! USEFUL FOR CHECKING ITEM SWAPPING
        # print('')
        # print('')
        # print('-'*len(self.chapterName))
        # print(self.chapterName)
        # print('-'*len(self.chapterName))
        # print('')
        # with open(get_filename('json/itemNames.json'),'r') as file:
        #     itemNames = hjson.load(file)
        
        # Place sampled items
        for placeList in self.places.values():
            for place in placeList:
                itemList = place.getItemList()
                newItemList = []
                for i, (_, item, num) in zip(place.itemIndices, itemList):
                    # Get worth of vanilla item
                    if item in Chapter.buyPrice:
                        if num == 0:
                            worth = Chapter.buyPrice[item]
                        else:
                            worth = Chapter.buyPrice[item] * num
                    else:
                        assert item == 'ITEM_MONEY', item
                        worth = num
                    # Establish cost bounds of new item
                    minWorth = int(worth * 0.8)
                    maxWorth = int(worth * 1.4)

                    # Build list of candidates
                    candidates = []
                    for i, v in Chapter.buyPrice.items():
                        if i[:4] == 'NOTE': continue
                        if v > maxWorth:
                            continue
                        p = random.randint(minWorth, maxWorth)
                        if v > minWorth:
                            candidates.append((i, 1, p))
                        n = p // v
                        if n and n < 5:
                            candidates.append((i, n, p))

                    # Pick an item
                    newItemList.append(random.sample(candidates, 1)[0])

                    ### DON'T DELETE! USEFUL FOR CHECKING ITEM SWAPPING
                    # newItem, newItemNum, newMoney = newItemList[-1]
                    # if item != 'ITEM_MONEY':
                    #     l1 = f"{itemNames[item]}"
                    #     if num > 1:
                    #         l2 = f"x{num}"
                    #     else:
                    #         l2 = ''
                    #     l3 = str(worth)
                    #     l4 = str(minWorth)
                    #     l5 = str(maxWorth)
                    #     l6 = f"{itemNames[newItem]} x{newItemNum} OR Money {newMoney}"
                    # else:
                    #     l1 = f"Money"
                    #     l2 = ''
                    #     l3 = str(worth)
                    #     l4 = str(minWorth)
                    #     l5 = str(maxWorth)
                    #     l6 = f"{itemNames[newItem]} x{newItemNum} OR Money {newMoney}"
                    # print('  ', l1.rjust(40, ' '), l2.rjust(4, ' '), l3.rjust(6, ' '), '<--', l4.rjust(5, ' '), '--', l5.rjust(5, ' '), l6)

                random.shuffle(newItemList)
                for index, (item, count, money) in zip(place.itemIndices, newItemList):
                    if random.random() < 0.15:
                        place.setItem(index, 'ITEM_MONEY', money)
                    else:
                        place.setItem(index, item, count)

    def update(self):
        if not self.places: return
        for placeList in self.places.values():
            for place in placeList:
                place.update()

# def research_item_modding_demo(pak):
#     print('Research Item Modding Demo')

#     research = ResearchItems(pak, 'A1_EX_Street_R_OTH_ms02_x02.umap')    

#     research.changeItem(10, 'ITEM_BATTLE_MAGIC_FIRE', 10)
#     research.changeItem(11, 'ITEM_CLASSMEDAL_HIGH', 4)
#     research.changeItem(12, 'BATTLE_ACCESSARY_IMMORTAL_PLUME', 42)

#     x, y, z = research.getLocation(12)
#     research.setLocation(12, x+900.0, y+500.0, z-38.0*4)

#     research.update()


def research_item_randomize(pak):
    with open(get_filename('json/researchData.json'), 'r') as file:
        researchData = hjson.load(file)

    chapterList = []
    for chapterName, data in researchData.items():
        chapterList.append(Chapter(pak, chapterName, data))

    return chapterList

def research_spoiler(chapterList, *args):
    outfile = os.path.join(*args)
    with open(get_filename('json/itemNames.json'),'r') as file:
        itemNames = hjson.load(file)

    with open(outfile, 'w') as sys.stdout:
        for chapter in chapterList:
            n = len(chapter.chapterName)
            print('-'*(n+2))
            print('',chapter.chapterName,'')
            print('-'*(n+2))
            print('')
            if chapter.places is None:
                print('   None')
                print('')
                continue

            for placeName, placeList in chapter.places.items():
                itemList = [place.getItemList() for place in placeList]
                if not any(itemList): continue
                print('  ', placeName)
                for p, i in zip(placeList, itemList):
                    for index, item, count in i:
                        if count == 0:
                            item = itemNames[item]
                            print('      ', item)
                        elif item == 'ITEM_MONEY':
                            print('      ', count, 'money')
                        elif item[:4] == 'NOTE':
                            item = itemNames[item]
                            print('      ', item)
                        else:
                            item = itemNames[item]
                            print('      ', item, f'x{count}')
                print('')
            print('')

    sys.stdout = sys.__stdout__
