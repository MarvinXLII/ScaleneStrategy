from Assets import Data
import random
import hjson
import os
import sys
from Text import Text
from Utility import get_filename


class Jobs:
    def __init__(self, pak):
        self.job = Data(pak, 'GOP_Battle_Job.uasset')
        self.jobData = self.job.getDataTable()
        self.ability = Data(pak, 'GOP_Battle_Ability.uasset')
        self.abilityData = self.ability.getDataTable()
        self.abilityText = Text(pak, 'en/GOP_Text_Ability.uasset')

        # Print all supports and commands
        self.namesForPrinting = {}
        self.supportSkills = []
        self.commandSkills = []
        self.skillType = {}
        for key, data in self.abilityData.items():
            self.namesForPrinting[key] = None
            nameKey = data['AbilityName'].name
            helpKey = data['AbilityHelp'].name
            try:
                d = {
                    'name': self.abilityText.getText(nameKey),
                    'help': self.abilityText.getText(helpKey),
                }
            except:
                continue

            self.namesForPrinting[key] = d
            if data['eAbilityCategory'].value == 'EAbilityCategory::COMMAND':
                self.commandSkills.append(key)
                self.skillType[key] = 'Command'
            elif data['eAbilityCategory'].value == 'EAbilityCategory::SUPPORT':
                if '[Passive Skill]' in self.namesForPrinting[key]['help']:
                    self.supportSkills.append(key)
                    self.skillType[key] = 'Support'
            else:
                self.skillType[key] == 'Other'

        ### LOAD WEIGHTS
        with open(get_filename('json/abilityWeights.json'), 'r') as file:
            data = hjson.load(file)
            self.abilityWeights = data['weights']
            self.abilityWeightKeys = data['abilities']
            self.abilityWeightNames = data['abilityNames']
            self.skipAbility = data['skipAbility']

        # Map weights keys to jobData keys
        self.weightsToData = {k:[] for k in self.abilityWeights.keys()}
        for key in self.jobData.keys():
            k = key[:18]
            if k in self.weightsToData:
                self.weightsToData[k].append(key)

    def randomSupport(self):
        # Sort orders by weights
        x = list(self.abilityWeights.items())
        random.shuffle(x)
        keys, _ = zip(*sorted(x, key=lambda xi: sum(xi[1])))
        avail = {k:True for k in self.abilityWeightKeys}
        unitsWithCounter = {k:None for k in self.abilityWeights}  # TODO: update animations, may need this stored data if done elsewhere
        counterKeys = {a:False for a in self.abilityWeightKeys}
        counterKeys['BATTLE_ABILITY_COUNTER_FORM'] = True
        counterKeys['BATTLE_ABILITY_PHYSICS_COUNTER'] = True
        counterKeys['BATTLE_ABILITY_COUNTER_FORM_P021'] = True
        counterKeys['BATTLE_ABILITY_CROSS_COUNTER'] = True
        for key in keys:
            skills = []
            numSup = [0]*len(self.weightsToData[key])
            for n, dKey in enumerate(self.weightsToData[key]):
                classSkills = []
                for i in range(1, 11):
                    aKey = f'LearnableAbility{i}'
                    abilityKey = self.jobData[dKey][aKey].name
                    if abilityKey == 'None': continue
                    if self.skillType[abilityKey] == 'Support':
                        if self.skipAbility[abilityKey]: ### WILL SKIP ABILITIES THAT MUST BE PAIRED, TODO!!!
                            continue
                        lKey = f'iLearnableLevel{i}'
                        skills.append((self.jobData[dKey][lKey], self.jobData[dKey][aKey]))
                        numSup[n] += 1

            if skills:
                w = [x*y for x,y in zip(self.abilityWeights[key], avail.values())]
                while True:
                    abilities = random.choices(self.abilityWeightKeys, w, k=len(skills))

                    # Ensure no unit gets more than 1 counter ability.
                    numCounters = 0
                    for a in abilities:
                        numCounters += counterKeys[a]
                    if numCounters > 2:
                        continue

                    ##### SPECIAL PAIRINGS #####
                    if len(skills) >= 2:
                        ##### Prohibiting TP recovery belongs to Decimal, NOT Automaton's Artifice.
                        ##### For now just keep these on Decimal. Hopefully I'll find some other way to handle this.
                        # # Automaton's Artifice & Charge TP
                        # hasAutomatonsArtifice = 'BATTLE_ABILITY_INSTRUMENT' in abilities
                        # if numSup[0] >= 2 and avail['BATTLE_ABILITY_INSTRUMENT'] and hasAutomatonsArtifice:
                        #     j = abilities.index('BATTLE_ABILITY_INSTRUMENT')
                        #     abilities = abilities[j:] + abilities[:j]
                        #     abilities[1] = 'BATTLE_ABILITY_WAIT_CHARGE'
                        #     skills[0][0].value = 1
                        #     skills[1][0].value = 1
                        # elif hasAutomatonsArtifice: # Don't allow this skill unless it can be paired with Charge TP
                        #     continue

                        # Increase steal rate
                        if avail['BATTLE_ABILITY_INCRASE_STEAL_RATE'] and ('BATTLE_ABILITY_PURSUIT_STEAL' in abilities or 'BATTLE_ABILITY_ITEM_CATCH' in abilities):
                            try:
                                j = abilities.index('BATTLE_ABILITY_PURSUIT_STEAL')
                            except:
                                j = abilities.index('BATTLE_ABILITY_ITEM_CATCH')
                            while True:
                                k = random.randint(0, len(skills)-1)
                                if j != k: break
                            abilities[k] = 'BATTLE_ABILITY_INCRASE_STEAL_RATE'
                            if j > k:
                                abilities[j], abilities[k] = abilities[k], abilities[j]

                    break

                for a, (_, abl) in zip(abilities, skills):
                    abl.name = a
                    avail[a] = False
                    if counterKeys[a]:
                        unitsWithCounter[key] = a
                        # TODO: UPDATE ANIMATION

    def update(self):
        self.job.update()

    def spoilers(self, *args):
        k2n = {
            'BATTLE_JOB_CH_P001': 'Serenoa',
            'BATTLE_JOB_CH_P002': 'Roland',
            'BATTLE_JOB_CH_P003': 'Benedict',
            'BATTLE_JOB_CH_P004': 'Frederica',
            'BATTLE_JOB_CH_P005': 'Geela',
            'BATTLE_JOB_CH_P006': 'Anna',
            'BATTLE_JOB_CH_P007': 'Hughette',
            'BATTLE_JOB_CH_P008': 'Erador',
            'BATTLE_JOB_CH_P009': 'Rudolph',
            'BATTLE_JOB_CH_P010': 'Corentin',
            'BATTLE_JOB_CH_P011': 'Julio',
            'BATTLE_JOB_CH_P012': 'Milo',
            'BATTLE_JOB_CH_P013': 'Cordelia',
            'BATTLE_JOB_CH_P014': 'Travis',
            'BATTLE_JOB_CH_P015': 'Trish',
            'BATTLE_JOB_CH_P016': 'Avlora',
            'BATTLE_JOB_CH_P017': 'Hossabara',
            'BATTLE_JOB_CH_P018': 'Narve',
            'BATTLE_JOB_CH_P019': 'Medina',
            'BATTLE_JOB_CH_P020': 'Jens',
            'BATTLE_JOB_CH_P021': 'Maxwell',
            'BATTLE_JOB_CH_P022': 'Archibald',
            'BATTLE_JOB_CH_P023': 'Flanagan',
            'BATTLE_JOB_CH_P024': 'Ezana',
            'BATTLE_JOB_CH_P025': 'Lionel',
            'BATTLE_JOB_CH_P026': 'Groma',
            'BATTLE_JOB_CH_P027': 'Piccoletta',
            'BATTLE_JOB_CH_P028': 'Decimal',
            'BATTLE_JOB_CH_P029': 'Quahaug',
            'BATTLE_JOB_CH_P030': 'Giovanna',
        }

        outfile = os.path.join(*args)

        ### PRINT ALL JOB DATA
        with open(outfile, 'w') as sys.stdout:
            unit = ''
            for key, data in self.jobData.items():
                if key[:16] != 'BATTLE_JOB_CH_P0':
                    continue
                stringList = []
                for i in range(1, 11):
                    level = str(data[f'iLearnableLevel{i}'].value).rjust(3, ' ')
                    abilityKey = data[f'LearnableAbility{i}'].name
                    if abilityKey[:4] == 'None': continue
                    abilityName = self.namesForPrinting[abilityKey]['name'].ljust(35, ' ')
                    abilityHelp = self.namesForPrinting[abilityKey]['help']
                    abilityKey = abilityKey.ljust(38, ' ')
                    if '[Passive Skill]' in abilityHelp:
                        stringList.append([level, abilityName, '(Passive Skill)'])#, abilityKey, abilityHelp])
                    else:
                        stringList.append([level, abilityName])#, abilityKey, abilityHelp])
                if stringList:
                    for k, v in k2n.items():
                        if k in key:
                            n = v
                            break
                    else:
                        sys.exit()
                    if unit != n:
                        unit = n
                        print(unit)
                    for s in stringList:
                        print('  ', *s)
                    print('')
            print('')
            print('')
        sys.stdout = sys.__stdout__
