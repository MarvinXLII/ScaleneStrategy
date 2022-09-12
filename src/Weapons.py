from Assets import Data
import random
from copy import deepcopy
import hjson
import os


# Exclusives and preconditions are randomly swapped right now.
# This should be reviewed and possibly redesigned after shuffling
# around abilities.
class WeaponAbilityTree:
    def __init__(self, pak):
        self.gop = Data(pak, 'GOP_Battle_WeaponAbilityTree.uasset')
        self.data = self.gop.getDataTable()

    def randomExclusives(self):
        # Count the total number of exclusives
        count = 0
        slots = 0
        for p in range(1, 31):
            pi = str(p).rjust(3, '0')
            for r in range(1, 3): # Don't include rank 3
                k = f"BATTLE_WEAPONABILITYTREE_P{pi}_RANK{r}"
                v = self.data[k]
                slots += 2
                count += v['bExclusive1_2'].value
                count += v['bExclusive3_4'].value

        # Randomly set the exclusives
        b = [True]*count + [False]*(slots-count)
        random.shuffle(b)
        for p in range(1, 31):
            pi = str(p).rjust(3, '0')
            for r in range(1, 3): # Don't include rank 3
                k = f"BATTLE_WEAPONABILITYTREE_P{pi}_RANK{r}"
                v = self.data[k]
                v['bExclusive1_2'].value = b.pop()
                v['bExclusive3_4'].value = b.pop()

    def randomPreconditions(self):
        # Store candidates (i.e. omit r2 slot if there is not r3 ability)
        candidates = []
        count = 0
        for p in range(1, 31):
            pi = str(p).rjust(3, '0')
            for r in range(1, 3):
                v1 = self.data[f"BATTLE_WEAPONABILITYTREE_P{pi}_RANK{r}"]
                v2 = self.data[f"BATTLE_WEAPONABILITYTREE_P{pi}_RANK{r+1}"]
                for i in range(2, 6):
                    a = f"AbilityId{i}"
                    b = f"bPrecondition{i}"
                    if v2[a].name != 'None':
                        candidates.append(v1[b])
                    count += v1[b].value
                    v1[b].value = False

        b = [True]*count + [False]*(len(candidates)-count)
        random.shuffle(b)
        for c in candidates:
            c.value = b.pop()

    def update(self):
        self.gop.update()


class Weapon:
    def __init__(self, pak):
        self.gop = Data(pak, 'GOP_Battle_Weapon.uasset')
        self.data = self.gop.getDataTable()

    def _shuffle(self, r):
        keys = [f"BATTLE_WEAPON_RANK{r}_P" + str(i).rjust(3, '0') for i in range(1, 31)]
        for i, ki in enumerate(keys):
            kj = random.sample(keys[i:], 1)[0]
            self.data[ki]['RankUpMaterial1'], self.data[kj]['RankUpMaterial1'] = \
                self.data[kj]['RankUpMaterial1'], self.data[ki]['RankUpMaterial1']

    def shuffleMaterial(self):
        self._shuffle(2) # Rank 2
        self._shuffle(3) # Rank 3

    def update(self):
        self.gop.update()


# Menus are capped at 12 units per material
class WeaponMaterial:
    def __init__(self, pak):
        self.gop = Data(pak, 'GOP_Battle_WeaponAbilityMaterial.uasset')
        self.data = self.gop.getDataTable()

        # Fill in dagger for fair swapping
        dagger_r3 = self.data['BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_DAGGER_RANK3']
        dagger_r3['MaterialId1_4'].name = 'ITEM_UPGRADEMATERIAL_LVUP_STONE_RANK3'
        dagger_r3['MaterialId2_4'].name = 'ITEM_UPGRADEMATERIAL_LVUP_IRON_RANK3'
        dagger_r3['MaterialId1_5'].name = 'ITEM_UPGRADEMATERIAL_LVUP_STONE_RANK3'
        dagger_r3['MaterialId2_5'].name = 'ITEM_UPGRADEMATERIAL_LVUP_IRON_RANK3'
        dagger_r3['iMaterialNum1_4'].value = 15
        dagger_r3['iMaterialNum2_4'].value = 15
        dagger_r3['iMaterialNum1_5'].value = 20
        dagger_r3['iMaterialNum2_5'].value = 20

        # Number of units per weapon
        self.unitsPerWeapon = {
            'BOOK': 2,
            'BOW': 4,
            'CLUB': 2,
            'DAGGER': 2,
            'FAN': 1,
            'HAMMER': 1,
            'KNUCKLE': 1,
            'LACROSSE': 1,
            'PICKAXE': 1,
            'ROD': 2,
            'SHIELD': 2,
            'SPEAR': 2,
            'STICK': 4,
            'SWORD': 3,
            'TELESCOPE': 1,
            'WHIP': 1,
        }

        self.resources = ['WOOD', 'STONE', 'IRON', 'FIBER']
        self.materials = None

        self.templates = { # Number of materials, then rank
            1: {
                1: deepcopy(self.data['BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_SWORD_RANK1']),
                2: deepcopy(self.data['BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_SWORD_RANK2']),
                3: deepcopy(self.data['BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_SWORD_RANK3']),
            },
            2: {
                1: deepcopy(self.data['BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_KNUCKLE_RANK1']),
                2: deepcopy(self.data['BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_KNUCKLE_RANK2']),
                3: deepcopy(self.data['BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_KNUCKLE_RANK3']),
            }
        }

    def _assignMaterialsToWeapons(self):
        weapons = list(self.unitsPerWeapon.keys())
        mat = list(self.resources)
        matCnt = [12, 12, 12, 12]
        matWt = [0, 0, 0, 0]
        weaponMaterials = {k:[] for k in self.unitsPerWeapon.keys()}
        weights = [False]*len(weapons)

        def pickWeapon():
            for i, w in enumerate(weapons):
                slotAvail = len(weaponMaterials[w]) < 2
                matAvail = False
                for uj, cj in zip(mat, matCnt):
                    if uj not in weaponMaterials[w]: # if utility is not already set to this weapon
                        matAvail = cj >= self.unitsPerWeapon[w] # enough slots are available for this weapon
                    if matAvail:
                        break
                weights[i] = slotAvail * matAvail
            if any(weights):
                return random.choices(weapons, weights, k=1)[0]
            return 
        
        def assignMaterial(w):
            for i, c in enumerate(matCnt):
                matWt[i] = 0 if c < self.unitsPerWeapon[w] else self.unitsPerWeapon[w]

            # Pick resource
            i = random.choices([0,1,2,3], weights=matWt, k=1)[0]
            ki = mat[i]

            # Update resource weights
            matCnt[i] -= self.unitsPerWeapon[w]

            # Store the resource to the weapon
            weaponMaterials[w].append(ki)

        random.shuffle(weapons)
        for w in weapons:
            assignMaterial(w)

        while True:
            w = pickWeapon()
            if not w:
                break
            assignMaterial(w)

        matSlots = {k:0 for k in self.resources}
        for k, n in self.unitsPerWeapon.items():
            for u in weaponMaterials[k]:
                matSlots[u] += n

        constraintsMet = True
        for u, n in matSlots.items():
            constraintsMet *= n <= 12
        assert constraintsMet

        return weaponMaterials

    # Max number of units using each utility can be 12
    def shuffleByWeapon(self):
        self.materials = self._assignMaterialsToWeapons()
        keyRefs = list(self.data.keys())

        for w, m in self.materials.items():
            w1 = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{w}_RANK1'
            w2 = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{w}_RANK2'
            w3 = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{w}_RANK3'
            assert w1 in keyRefs
            assert w2 in keyRefs
            assert w3 in keyRefs

            m = self.materials[w]
            if len(m) == 1:
                self.data[w1] = deepcopy(self.templates[1][1])
                self.data[w2] = deepcopy(self.templates[1][2])
                self.data[w3] = deepcopy(self.templates[1][3])
            
                m1 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[0]}_RANK1'
                m2 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[0]}_RANK2'
                m3 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[0]}_RANK3'

                for i in range(1, 6):
                    self.data[w1][f'MaterialId1_{i}'].name = m1
                    self.data[w2][f'MaterialId1_{i}'].name = m2
                    self.data[w3][f'MaterialId1_{i}'].name = m3
                for i in range(4, 6):
                    self.data[w1][f'MaterialId2_{i}'].name = m2
                    self.data[w2][f'MaterialId2_{i}'].name = m3

            elif len(m) == 2:
                self.data[w1] = deepcopy(self.templates[2][1])
                self.data[w2] = deepcopy(self.templates[2][2])
                self.data[w3] = deepcopy(self.templates[2][3])
                
                m1_1 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[0]}_RANK1'
                m2_1 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[0]}_RANK2'
                m3_1 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[0]}_RANK3'

                m1_2 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[1]}_RANK1'
                m2_2 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[1]}_RANK2'
                m3_2 = f'ITEM_UPGRADEMATERIAL_LVUP_{m[1]}_RANK3'

                for i in range(1, 6):
                    self.data[w1][f'MaterialId1_{i}'].name = m1_1
                    self.data[w2][f'MaterialId1_{i}'].name = m2_1
                    self.data[w3][f'MaterialId1_{i}'].name = m3_1
                    self.data[w3][f'MaterialId2_{i}'].name = m3_2
                for i in range(1, 4):
                    self.data[w1][f'MaterialId2_{i}'].name = m1_2
                    self.data[w2][f'MaterialId2_{i}'].name = m2_2
                for i in range(4, 6):
                    self.data[w1][f'MaterialId2_{i}'].name = m2_2
                    self.data[w2][f'MaterialId2_{i}'].name = m3_2

            else:
                sys.exit(f"weapons must have 1 or 2 materials; weapon {w} has {m}")
        
        # for i, ki in enumerate(self.weapons):
        #     kj = random.sample(self.weapons[i:], 1)[0]
        #     for r in range(1, 4):
        #         wi = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{ki}_RANK{r}'
        #         wj = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{kj}_RANK{r}'
        #         self.data[wi], self.data[wj] = self.data[wj], self.data[wi]

    # def shuffleWithinRanks(self):
    #     for r in range(1, 4):
    #         for i, ki in enumerate(self.weapons):
    #             kj = random.sample(self.weapons[i:], 1)[0]
    #             wi = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{ki}_RANK{r}'
    #             wj = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{kj}_RANK{r}'
    #             self.data[wi], self.data[wj] = self.data[wj], self.data[wi]

    # def shuffleAll(self):
    #     countMaterials = {}
    #     for r in range(1, 4):
    #         for n in range(1, 6):
    #             for i, ki in enumerate(self.weapons):
    #                 kj = random.sample(self.weapons[i:], 1)[0]
    #                 wi = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{ki}_RANK{r}'
    #                 wj = f'BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_{kj}_RANK{r}'

    #                 mat1 = f"MaterialId1_{n}"
    #                 mat2 = f"MaterialId2_{n}"
    #                 self.data[wi][mat1], self.data[wj][mat1] = self.data[wj][mat1], self.data[wi][mat1]
    #                 self.data[wi][mat2], self.data[wj][mat2] = self.data[wj][mat2], self.data[wi][mat2]

    #                 num1 = f"iMaterialNum1_{n}"
    #                 num2 = f"iMaterialNum2_{n}"
    #                 self.data[wi][num1], self.data[wj][num1] = self.data[wj][num1], self.data[wi][num1]
    #                 self.data[wi][num2], self.data[wj][num2] = self.data[wj][num2], self.data[wi][num2]

    #                 mon = f"iMoney_{n}"
    #                 self.data[wi][mon], self.data[wj][mon] = self.data[wj][mon], self.data[wi][mon]

    def update(self):
        # Cleanup dagger rank 3
        dagger_r3 = self.data['BATTLE_WEAPONABILITYMATERIAL_WEAPON_ABILITY_DAGGER_RANK3']
        dagger_r3['MaterialId1_4'].name = 'None'
        dagger_r3['MaterialId2_4'].name = 'None'
        dagger_r3['MaterialId1_5'].name = 'None'
        dagger_r3['MaterialId2_5'].name = 'None'
        dagger_r3['iMaterialNum1_4'].value = 0
        dagger_r3['iMaterialNum2_4'].value = 0
        dagger_r3['iMaterialNum1_5'].value = 0
        dagger_r3['iMaterialNum2_5'].value = 0

        # Make SelfId default
        for key, value in self.data.items():
            value['SelfId'].value = key

        # Now update
        self.gop.update()
