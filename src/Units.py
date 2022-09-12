from Assets import Data
from Utility import get_filename
import random
from Lub import Lub
from copy import deepcopy
import hjson
import os
import sys

class Units:
    def __init__(self, pak):

        # Omit Serenoa due to walking animation limitations
        self.keys = ['UNIT_MASTER_CH_P' + str(i).rjust(3, '0') for i in range(1, 31)]
        self.swap = {k:k for k in self.keys}

        # Needed only for entries; not updated
        self.gop_unit = Data(pak, 'GOP_Unit_Master.uasset')

        # GOP to update
        self.gop_vote = Data(pak, 'GOP_Unit_VoteParam.uasset')
        self.gop_tut = Data(pak, 'GOP_Tutorial.uasset')

        # Data for modding
        self.data_vote = self.gop_vote.getDataTable()
        self.data_tut = self.gop_tut.getDataTable()

        # Load files to be updated with swap
        self.lub_swap = Lub(pak, 'FuncDef.lub') # unit map table & modifies functions for unit joining/leaving party

        # Sprite swapping
        self.lub_sprite = Lub(pak, 'CharaCommon.lub')
        self.lub_sprite_talk = Lub(pak, 'CharaTalkBase.lub')

        # Update only with patches
        self.lub_misc = [
            # Common/sprites stuff
            self.lub_sprite,
            self.lub_sprite_talk,
            # Encampment
            Lub(pak, 'StandByEventData.lub'),
            # Voting
            Lub(pak, 'Scenario/CommonDef/PersuadeVoteTalkBase.lub'),
            Lub(pak, 'ms03_h01_vote_event.lub'),
	    Lub(pak, 'ms07_h01_vote_event.lub'),
            Lub(pak, 'ms07_h01_vote.lub'), # tweak to VoteEnd
	    Lub(pak, 'ms08a_h01_vote_event.lub'),
	    Lub(pak, 'ms08b_h01_vote_event.lub'),
	    Lub(pak, 'ms09_h01_vote_event.lub'),
	    Lub(pak, 'ms10a_h01_vote_event.lub'),
	    Lub(pak, 'ms11_h01_vote_event.lub'),
	    Lub(pak, 'ms13_h01_vote_event.lub'),
	    Lub(pak, 'ms15_h01_vote_event.lub'),
	    Lub(pak, 'ms17_h01_vote_event.lub'),
	    Lub(pak, 'ms16_x34_research_01_drama_sel.lub'),
            # Benedict -- calls chara for the swap table
            Lub(pak, 'TriggerMS01_X01.lub'),
            # Units join/leave party
            Lub(pak, 'ScenarioBlockJoinParty.lub'),
            Lub(pak, 'CommonDef/ScenarioBlock.lub'),
            # Regiment leads for Golden Ending
            Lub(pak, 'ms17_h01_a1_0080.lub'),
            Lub(pak, 'sb_ms17_h01_vt910_010.lub'),
            # Gold ending team split cutscenes
            Lub(pak, "EventCommon.lub"),
            Lub(pak, "ms17_h01_a1_0050.lub"),
            Lub(pak, "ms17_h01_a1_0060.lub"),
            Lub(pak, "ms17_h01_a1_0070.lub"),
            Lub(pak, "ms17s_x38_a1_0010.lub"),
            Lub(pak, "ms17s_x38_research_01_before.lub"),
            Lub(pak, "ms17s_x38_research_01_after.lub"),
            Lub(pak, "ms17s_x38_battle_01_before.lub"),
            Lub(pak, "ms17s_x38_battle_01_after.lub"),
            Lub(pak, "ms18s_x42_battle_01_before.lub"),
            Lub(pak, "ms18s_x42_battle_01_after.lub"),
            Lub(pak, "ms18s_x42_research_01_before.lub"),
            Lub(pak, "ms18s_x42_research_01_after.lub"),
            Lub(pak, "ms18s_x42_b0_0030.lub"),
            Lub(pak, "ms18f_x41_c0_1010.lub"),
            Lub(pak, "ms19s_x46_research_01_before.lub"),
            Lub(pak, "ms19s_x46_battle_01_before.lub"),
            Lub(pak, "ms19s_x46_battle_01_after.lub"),
            Lub(pak, "ms17s_x38_research_01_drama.lub"),
            Lub(pak, "ms18s_x42_research_01_drama.lub"),
            Lub(pak, "ms19s_x46_research_01_drama.lub"),
            # Cutscene crashes otherwise
            Lub(pak, 'ms06_x07_battle_01_after.lub'),
            Lub(pak, 'ms10a_f01_c0_2010.lub'),
            Lub(pak, 'ms14_x28_a0_0025.lub'),
            # Misc cutscene patches
            Lub(pak, 'ms01_x01_a0_0020.lub'),
            Lub(pak, 'ms17_h01_vote_110.lub'),
            Lub(pak, 'ms17_h01_vote_120.lub'),
            Lub(pak, 'ms17_h01_vote_130.lub'),
            # Data for cutscenes
            Lub(pak, 'UnitAttachedDataList.lub'),
            # Character Stories
            Lub(pak, 'cs24_e01_0010.lub'),
            Lub(pak, 'cs22_e01_0020.lub'),
            Lub(pak, 'cs15_e01_0010.lub'),
        ]

        # Speech bubbles
        self.data_speech = []
        with open(get_filename('txt/speech_files.txt'),'r') as file:
            for filename in file.readlines():
                if filename[0] == '#': continue
                filename = filename.strip('\n')
                self.data_speech.append(Data(pak, filename))

        self.data_speech_battles = {}
        with open(get_filename('json/speech_files_battles.json'),'r') as file:
            fileDict = hjson.load(file)
        for k, v in fileDict.items():
            data = Data(pak, k)
            self.data_speech_battles[data] = v

        # Map P??? to name (needed for tutorial)
        with open(get_filename('json/names.json'), 'r') as file:
            self.names = hjson.load(file)
            self.namesInv = {v:k for k,v in self.names.items()}

    def shuffleUnits(self, serenoa="UNIT_MASTER_CH_P001"):
        # Default weights for shuffling
        weights = {}
        for i in range(1, 31):
            j = str(i).rjust(3, '0')
            name = f"UNIT_MASTER_CH_P{j}"
            weights[name] = [True]*30

        #### Prevent shuffling issues ####

        # Serenoa
        # Currently not swapped due to limited controllable PCs
        weights['UNIT_MASTER_CH_P001'][1:] = [False]*29

        # Travis
        # Not allowed in first battle -> units P001-5
        weights['UNIT_MASTER_CH_P014'][:5] = [False]*5

        # Trish
        # Not allowed in first battle -> units P001-5
        weights['UNIT_MASTER_CH_P015'][:5] = [False]*5

        # Avlora
        # Not allowed in battles requiring Serenoa (and possibly Roland) -> units P001-2
        weights['UNIT_MASTER_CH_P016'][:2] = [False]*2

        ###################################

        # Shuffle with weighted sampling
        vacantSlot = [True]*30
        units = list(self.keys)
        random.shuffle(units)
        orderedKeys = sorted(units, key=lambda x: sum(weights[x]))
        tutorials = deepcopy(self.data_tut)
        for key in orderedKeys:
            # Swap units
            candidates = [i*j for i,j in zip(weights[key], vacantSlot)]
            idx = random.choices(range(len(self.keys)), weights=candidates, k=1)[0]
            assert vacantSlot[idx] == True, 'Already swapped!?'
            vacantSlot[idx] = False
            self.swap[self.keys[idx]] = key

            # Swap corresponding tutorial
            if key == 'UNIT_MASTER_CH_P001': # Serenoa has no tutorial!
                assert self.swap[key] == 'UNIT_MASTER_CH_P001'
                continue

            ni = self.names[key]
            nj = self.names[self.keys[idx]]
            ui = f'TUTORIAL_{ni.upper()}'
            uj = f'TUTORIAL_{nj.upper()}'
            self.data_tut[uj] = tutorials[ui]
            self.data_tut[uj]['SelfId'].name = uj

        # Update UnitRandomizer tables
        self.applySwapLub(self.lub_swap)

    def applySwapLub(self, lub):
        randomUnit = lub.getLocalTable('UnitRandomizer')
        randomUnit.setTable(self.swap)

    def applySwapAsset(self, data, skip=None):
        text = data.getDataTable()
        replace = {}
        for value in text.values():
            if skip and value['UnitMasterId'].name in skip:
                continue
            if value['UnitMasterId'].name in self.swap:
                default = value['UnitMasterId'].name
                value['UnitMasterId'].name = self.swap[default]
                replace[default] = self.swap[default]
        data.uasset.replaceIndices(replace)

    def getSwapUnitName(self, unitName):
        n = self.namesInv[unitName]
        s = self.swap[n]
        return self.names[s]

    def getSwapUnitNameDict(self):
        names = {}
        for k, v in self.swap.items():
            nk = self.names[k]
            nv = self.names[v]
            names[nk] = nv
        return names

    def simpleVoting(self):
        for key, value in self.data_vote.items():
            v = value['MoralThreshold'].value
            value['MoralThreshold'].value = 1 if v else 0
            v = value['BenefitThreshold'].value
            value['BenefitThreshold'].value = 1 if v else 0
            v = value['FreedomThreshold'].value
            value['FreedomThreshold'].value = 1 if v else 0

    def swapSprites(self):
        # Allows sprites to be swapped
        instr = self.lub_swap.chunkList[0].instrList[0]
        assert instr.name == 'LOADBOOL'
        assert instr.B == 0 # FALSE
        instr.B = 1

        # Update text bubbles
        for speech in self.data_speech:
            self.applySwapAsset(speech)

        for speech, skip in self.data_speech_battles.items():
            self.applySwapAsset(speech, skip)

        # Shuffle vote
        for k, v in self.data_vote.items():
            unit = v['UnitId'].name
            if unit in self.swap:
                v['UnitId'].name = self.swap[unit]
                self.gop_vote.uasset.addIndex(self.swap[unit])

    def update(self):
        self.gop_vote.update()
        self.gop_tut.update()
        self.lub_swap.update()
        
        for lub in self.lub_misc:
            lub.update()

        for data in self.data_speech:
            data.update()

        for data in self.data_speech_battles:
            data.update()

    def printUnits(self):
        for k,v in self.swap.items():
            kp = k.split('_')[-1]
            vp = v.split('_')[-1]
            print(self.names[k].ljust(15, ' ') + kp, '<--', self.names[v].ljust(15, ' ') + vp)

    def spoilers(self, *args):
        outfile = os.path.join(*args)
        with open(outfile, 'w') as sys.stdout:
            for k,v in self.swap.items():
                print(self.names[k].ljust(15, ' '), '<--', self.names[v].ljust(15, ' '))
        sys.stdout = sys.__stdout__
