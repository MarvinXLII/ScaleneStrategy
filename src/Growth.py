from Assets import Data
import random
import hjson
import os


class Growth:
    def __init__(self, pak):
        self.gop = Data(pak, 'GOP_Battle_UnitGrowth.uasset')
        self.data = self.gop.getDataTable()

    # Also tends to include allies....
    def weakEnemies(self):
        for key, value in self.data.items():
            if '_N005_' in key: # Symon; possibly others
                continue
            if "_M031" in key: # FAILED for Rosellan in "Fighting Idore the Deluded"; no clue why
                continue
            if "_M033" in key: # FAILED for Rosellan in "Fighting Idore the Deluded"; no clue why
                continue
            if "_M034" in key:
                continue
            if "_M035" in key: # Worked for Rosellan in "Fighting Idore the Deluded"; no clue why
                continue
            if "_M036" in key: # Worked for Rosellan in "Fighting Idore the Deluded"; no clue why
                continue
            if "_CH_P" in key:
                continue
            # value['fUnitSpeed'].value = 1.0
            value['fMaxHitPoint'].value = 3.0
            # value['fStrength'].value = 1.0
            # value['fIntelligence'].value = 1.0
            value['fDefence'].value = 1.0
            value['fMagicDefence'].value = 1.0
            value['fAgility'].value = 1.0
            # value['fDexterity'].value = 1.0  # "Accuracy"
            value['fLuck'].value = 1.0
        # sys.exit()

    def update(self):
        self.gop.update()
