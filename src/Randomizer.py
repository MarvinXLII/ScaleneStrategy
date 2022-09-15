import os
import hjson
import shutil
import sys
sys.path.append('src')
from Pak import Pak
from Units import Units
from Level import Level, initLevels, randomizeLevelInits
from Text import TextAll
from Maps import MapCfg
from Items import Accessories, ClassMedal, ItemBattle, UpgradeMaterial, Shops, research_item_randomize, research_spoiler
from Weapons import WeaponAbilityTree, WeaponMaterial, Weapon
from Growth import Growth
from World import World
from Jobs import Jobs
import random
from dataclasses import dataclass

@dataclass
class RNGSeed:
    seed: int

    # Start on a new seed every time to allow for toggling options on/off while
    # preserving all other settings
    def setSeed(self):
        random.seed(self.seed)
        self.seed += 1


class Rando:
    def __init__(self, pak, settings):
        self.pak = pak
        self.settings = settings
        self.seed = RNGSeed(self.settings['seed'])

        self.outPath = f"seed_{self.settings['seed']}"
        if not os.path.isdir(self.outPath):
            os.makedirs(self.outPath)

        self.units = Units(pak)
        self.jobs = Jobs(pak)
        self.text = TextAll(pak)
        self.mapcfg = MapCfg(pak)
        self.accessories = Accessories(pak)
        self.medals = ClassMedal(pak)
        self.battleitems = ItemBattle(pak)
        self.materials = UpgradeMaterial(pak)
        self.shops = Shops(pak)
        self.wpnTree = WeaponAbilityTree(pak)
        self.wpnMat = WeaponMaterial(pak)
        self.wpn = Weapon(pak)
        self.growth = Growth(pak)
        self.world = World(pak)
        self.levels = initLevels(pak)
        self.research = research_item_randomize(pak)

    def failed(self):
        print(f"Randomizer failed! Removing directory {self.outPath}.")
        shutil.rmtree(self.outPath)

    def randomize(self):
        self.text.updateMainScreen()

        # Item buy/sell costs
        self.seed.setSeed()
        if self.settings['random-item-costs']:
            self.accessories.randomCost(25)
            self.medals.randomCost(50)
            self.battleitems.randomCost(50)
            self.materials.randomCost(40)

        self.seed.setSeed()
        if self.settings['random-inventory-numbers']:
            self.shops.randomInventory()

        # Class stuff
        self.seed.setSeed()
        if self.settings['random-class-support-skills']:
            self.jobs.randomSupport()

        # Weapon trees
        self.seed.setSeed()
        if self.settings['random-weapon-exclusives']:
            self.wpnTree.randomExclusives()

        self.seed.setSeed()
        if self.settings['random-weapon-preconditions']:
            self.wpnTree.randomPreconditions()

        # Weapon material costs
        self.seed.setSeed()
        if self.settings['random-weapon-materials']:
            self.wpnMat.shuffleByWeapon()
        # if WEAPONMATERIALCOSTS == 'Weapons':
        #     self.wpnMat.shuffleByWeapon()
        # elif WEAPONMATERIALCOSTS == 'Ranks':
        #     self.wpnMat.shuffleWithinRanks()
        # elif WEAPONMATERIALCOSTS == 'All':
        #     self.wpnMat.shuffleAll()

        # Weapon rank costs
        self.seed.setSeed()
        if self.settings['shuffle-class-rank-items']:
            self.wpn.shuffleMaterial()

        # Weather and wind
        self.seed.setSeed()
        if self.settings['shuffle-battle-weather']:
            self.mapcfg.shuffleWeather()
            self.mapcfg.shuffleWind()

        # Time
        # self.seed.setSeed()
        if self.settings['shuffle-battle-time']:
            self.mapcfg.shuffleTimes()

        # Swap playable units
        self.seed.setSeed()
        if self.settings['shuffle-playable-units']:
            self.units.shuffleUnits()
            for level in self.levels:
                level.updateEnforcedPCs(self.units.swap)
            self.world.charaStoryIcons(self.units.swap)
            self.text.swapVictoryCondition(self.units)

            # Swap Sprites & Text
            if self.settings['update-playable-unit-sprites']:
                self.units.swapSprites()
                self.text.swapSpriteNames(self.units)

        if self.settings['random-battle-unit-placement']:
            if 'testing' in self.settings:
                randomizeLevelInits(self.levels, self.settings['seed'], self.pak, test=self.settings['testing'])
            else:
                randomizeLevelInits(self.levels, self.settings['seed'], self.pak, test=False)

        # Shuffle starting turn order
        self.seed.setSeed()
        if self.settings['shuffle-battle-initial-charge-times']:
            for level in self.levels:
                level.randomTimes()

        self.seed.setSeed()
        if self.settings['random-exploration-items']:
            for chapter in self.research:
                chapter.randomItems()

    def qualityOfLife(self):
        # Voting
        if self.settings['qol-easier-voting']:
            self.units.simpleVoting()

        # Remove Serenoa
        if self.settings['qol-serenoa-optional']:
            for level in self.levels[1:]: # Skip the first level
                level.removeSerenoa()

        # My own testing stuff....
        if 'testing' in self.settings:
            if self.settings['testing']:
                self.growth.weakEnemies()
                # self.world.simpleCharaStories()

    def spoilerLog(self):
        if self.settings['shuffle-playable-units']:
            self.units.spoilers(self.outPath, 'shuffled_units.log')

        if self.settings['random-class-support-skills']:
            self.jobs.spoilers(self.outPath, 'random_support_skills.log')

        if self.settings['random-exploration-items']:
            research_spoiler(self.research, self.outPath, 'random_items.log')

    def dump(self, fileName):
        self.text.update()
        self.units.update()
        self.mapcfg.update()
        self.accessories.update()
        self.medals.update()
        self.battleitems.update()
        self.jobs.update()
        self.materials.update()
        self.shops.update()
        self.wpnTree.update()
        self.wpnMat.update()
        self.wpn.update()
        self.growth.update()
        self.world.update()
        for level in self.levels:
            level.update()
        for research in self.research:
            research.update()

        self.pak.buildPak(fileName)

        self.spoilerLog()

        settingsOutput = os.path.join(self.outPath, 'settings.json')
        with open(settingsOutput, 'w') as file:
            hjson.dump(self.settings, file)
        with open('settings.json', 'w') as file:
            hjson.dump(self.settings, file)


class Switch(Rando):
    def __init__(self, pak, settings):
        super(Switch, self).__init__(pak, settings)

    def dump(self):
        pakPath = os.path.join(self.outPath, '0100CC80140F8000', 'romfs', 'Newera', 'Content', 'Paks')
        if not os.path.isdir(pakPath):
            os.makedirs(pakPath)
        pakName = os.path.join(pakPath, 'Newera-Switch_P.pak')
        super(Switch, self).dump(pakName)
