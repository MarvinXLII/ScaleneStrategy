from Assets import Data
import random
import hjson
import os


class World:
    def __init__(self, pak):
        self.gop = Data(pak, 'GOP_World_Icon.uasset')
        self.data = self.gop.getDataTable()
        self.convictions = None
        self.swap = None

    def charaStoryIcons(self, swap):
        for k, v in self.data.items():
            gopId = v['UnitMasterGopIdMatching'].name
            if gopId in swap:
                v['UnitMasterGopIdMatching'].name = swap[gopId]
        self.swap = swap

    # Only changes conviction values and battle requirements
    # No changes to story progression requirements
    def simpleCharaStories(self):
        for k, v in self.data.items():
            if 'WORLD_ICON_CS' not in k:
                continue
            if v['BattleAttendanceRequirement'].value:
                v['BattleAttendanceRequirement'].value = 1
            else:
                v['FaithParamRequirement'].value = 1
                v['FaithParamRequirement_02'].value = 1
                v['FaithParamRequirement_03'].value = 1

    def charaStoryConvictions(self):
        assert self.swap == None, "Must do this BEFORE swapping icons to simplify printouts"
        # Gather data
        self.convictions = {}
        for k, v in self.data.items():
            req1 = v['FaithTypeRequirement'].value
            if req1 == 'EFaithType::NONE':
                continue
            req2 = v['FaithTypeRequirement_02'].value
            req3 = v['FaithTypeRequirement_03'].value
            val1 = v['FaithParamRequirement'].value
            val2 = v['FaithParamRequirement_02'].value
            val3 = v['FaithParamRequirement_03'].value
            gopId = v['UnitMasterGopIdMatching'].name
            assert gopId not in self.convictions
            self.convictions[gopId] = {
                req1: val1,
                req2: val2,
                req3: val3,
            }

        # Shuffle
        keys = list(self.convictions.keys())
        for i, ki in enumerate(self.convictions.keys()):
            kj = random.sample(keys[i:], 1)[0]
            self.convictions[ki], self.convictions[kj] = self.convictions[kj], self.convictions[ki]

        # Store data
        for k, v in self.data.items():
            gopId = v['UnitMasterGopIdMatching'].name
            if gopId not in self.convictions:
                continue
            v['FaithTypeRequirement'].value = 'EFaithType::BENEFIT'
            v['FaithTypeRequirement_02'].value = 'EFaithType::MORAL'
            v['FaithTypeRequirement_03'].value = 'EFaithType::FREEDOM'
            v['FaithParamRequirement'].value = self.convictions[gopId]['EFaithType::BENEFIT']
            v['FaithParamRequirement_02'].value = self.convictions[gopId]['EFaithType::MORAL']
            v['FaithParamRequirement_03'].value = self.convictions[gopId]['EFaithType::FREEDOM']

    def update(self):
        self.gop.update()
