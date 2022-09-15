from Assets import Data


class Text:
    def __init__(self, pak, filename):
        self.data = Data(pak, filename)
        self.uasset = self.data.uasset
        self.text = self.data.getDataTable()

    def getText(self, key):
        return self.text[key]['Text'].string

    def setText(self, key, string):
        self.text[key]['Text'].string = string

    def replaceSubstring(self, key, targ, repl):
        t = self.text[key]['Text'].string
        r = t.replace(targ, repl)
        self.text[key]['Text'].string = r

    def replaceAllSubstrings(self, mapping):
        string2tmp = {}
        tmp2string = {}
        for i, (k, v) in enumerate(mapping.items()):
            index = str(i).rjust(3, '0')
            tmp = f'TMP_{index}'
            string2tmp[k] = tmp # string to tmp
            tmp2string[tmp] = v # tmp to new string

        for key in self.text.keys():
            for s, t in string2tmp.items():
                self.replaceSubstring(key, s, t)
            for t, s in tmp2string.items():
                self.replaceSubstring(key, t, s)

    def update(self):
        self.data.update()

class TextAll:
    def __init__(self, pak):
        self.common = Text(pak, 'en/GOP_Text_Common.uasset')
        self.ms15_x32 = Text(pak, 'en/Main/ms15_x32/Text_ms15_x32_a1_0010.uasset')
        self.systemMessage = Text(pak, 'Text/en/GOP_Text_System_Message.uasset')
        self.swap_all = [
            Text(pak, 'Text/en/GOP_Text_EventOverview.uasset'),
            Text(pak, 'Text/en/GOP_Text_StoryChart.uasset'),
            Text(pak, 'en/Main/ms02_x02/Text_ms02_x02_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms02_x02/Text_ms02_x02_research_02_drama.uasset'),
            Text(pak, 'en/Main/ms03_h01/Text_ms03_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms03_h01/Text_ms03_h01_persuade_research_drama.uasset'),
            Text(pak, 'en/Main/ms03_x03/Text_ms03_x03_part_research_01_drama_01.uasset'),
            Text(pak, 'en/Main/ms03_x03/Text_ms03_x03_part_research_01_drama_02.uasset'),
            Text(pak, 'en/Main/ms03_x03/Text_ms03_x03_research_01_drama_01.uasset'),
            Text(pak, 'en/Main/ms03_x03/Text_ms03_x03_research_01_drama_02.uasset'),
            Text(pak, 'en/Main/ms03_x03/Text_ms03_x04_research_01_drama_01.uasset'),
            Text(pak, 'en/Main/ms03_x04/Text_ms03_x04_research_01_drama_01.uasset'),
            Text(pak, 'en/Main/ms03_x04/Text_ms03_x04_research_01_drama_02.uasset'),
            Text(pak, 'en/Main/ms04_x05/Text_ms04_x05_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms04_x05/Text_ms04_x05_research_02_drama.uasset'),
            Text(pak, 'en/Main/ms05_x06/Text_ms05_x06_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms06_x07/Text_ms06_x07_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms07_h01/Text_ms07_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms07_h01/Text_ms07_h01_persuade_research_drama.uasset'),
            Text(pak, 'en/Main/ms07_x08/Text_ms07_x08_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms07_x09/Text_ms07_x09_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms08a_h01/Text_ms08a_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms08a_h01/Text_ms08a_h01_persuade_research_drama_01.uasset'),
            Text(pak, 'en/Main/ms08a_h01/Text_ms08a_h01_persuade_research_drama_02.uasset'),
            Text(pak, 'en/Main/ms08a_x10/Text_ms08a_x10_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms08a_x11/Text_ms08a_x11_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms08b_h01/Text_ms08b_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms08b_h01/Text_ms08b_h01_persuade_research_drama.uasset'),
            Text(pak, 'en/Main/ms08b_h01/Text_ms08b_h01_persuade_research_drama_01.uasset'),
            Text(pak, 'en/Main/ms08b_x12/Text_ms08b_x12_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms08b_x13/Text_ms08b_x13_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms09_h01/Text_ms09_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms09_h01/Text_ms09_h01_persuade_research_drama_01.uasset'),
            Text(pak, 'en/Main/ms09_h01/Text_ms09_h01_persuade_research_drama_02.uasset'),
            Text(pak, 'en/Main/ms09_x14/Text_ms09_x14_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms09_x15/Text_ms09_x15_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms10a_h01/Text_ms10a_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms10a_h01/Text_ms10a_h01_persuade_research_drama.uasset'),
            Text(pak, 'en/Main/ms10a_x16/Text_ms10a_x16_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms10b_h01/Text_ms10b_h01_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms11_h01/Text_ms11_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms11_h01/Text_ms11_h01_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms11_x21/Text_ms11_x21_research_01_drama.uasset'),
            # Text(pak, 'en/Main/ms12_h01/Text_ms12_h01_persuade_drama.uasset'), ### Content in different file??? Or no vote???
            Text(pak, 'en/Main/ms13_h01/Text_ms13_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms13_h01/Text_ms13_h01_persuade_research_drama.uasset'),
            Text(pak, 'en/Main/ms13_x24/Text_ms13_x24_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms13_x25/Text_ms13_x25_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms13_x26/Text_ms13_x26_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms15_h01/Text_ms15_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms15_h01/Text_ms15_h01_persuade_research_drama.uasset'),
            Text(pak, 'en/Main/ms15_x30/Text_ms15_x30_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms15_x31/Text_ms15_x31_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms15_x32/Text_ms15_x32_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms15_x33/Text_ms15_x33_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms16_x34/Text_ms16_x34_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms17_h01/Text_ms17_h01_persuade_drama.uasset'),
            Text(pak, 'en/Main/ms17_h01/Text_ms17_h01_persuade_research_drama.uasset'),
            Text(pak, 'en/Main/ms17s_x38/Text_ms17s_x38_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms18b_x39/Text_ms18b_x39_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms18f_x41/Text_ms18f_x41_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms18r_x40/Text_ms18r_x40_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms18s_x42/Text_ms18s_x42_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms19s_x46/Text_ms19s_x46_research_01_drama.uasset'),
            Text(pak, 'en/Main/ms20s_x47/Text_ms20s_x47_research_01_drama.uasset'),
        ]

    def update(self):
        self.common.update()
        self.ms15_x32.update()
        self.systemMessage.update()
        for text in self.swap_all:
            text.update()

    def updateMainScreen(self):
        self.common.setText('TEXT_COMMON_WEATHER_PRESS_ANY_BUTTON', 'Randomizer')

    def swapVictoryCondition(self, units):
        t = 'Roland'
        r = units.getSwapUnitName(t)
        self.common.replaceSubstring('TEXT_COMMON_BATTLE_UI_VICTORY_CONDITION_3', t, r)
        self.common.replaceSubstring('TEXT_COMMON_BATTLE_UI_DEFEAT_CONDITION_3', t, r)

    def swapSpriteNames(self, units):
        names = units.getSwapUnitNameDict()
        for text in self.swap_all:
            text.replaceAllSubstrings(names)
        
        t = 'Travis'
        r = units.getSwapUnitName(t)
        self.ms15_x32.replaceSubstring('MS15_X32_A1_0010_N_TTT_0010', t, r)

        t = 'Roland'
        r = units.getSwapUnitName(t)
        # self.common.replaceSubstring('TEXT_COMMON_BATTLE_UI_BATTLE_NAME_18_42', t, r)
        # self.common.replaceSubstring('TEXT_COMMON_THREE_SQUAD_ROLAND', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_07_HUD_AGENDA', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_07_HUD_OPINION_MS07_X08', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_07_HUD_OPINION_MS07_X09', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_07_OPINION_MS07_X08', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_07_OPINION_MS07_X09', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_10A_HUD_AGENDA', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_10A_HUD_OPINION_MS10A_X16', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_10A_HUD_OPINION_MS10A_X17', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_10A_OPINION_MS10A_X16', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_10A_OPINION_MS10A_X17', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_17_HUD_OPINION_MS17R_X36', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_17_OPINION_MS17R_X36', t, r)
        self.systemMessage.replaceSubstring('TEXT_SYSTEM_MESSAGE_DLG_MS05_X06_TUTORIAL_02', t, r)
        self.systemMessage.replaceSubstring('TEXT_SYSTEM_MESSAGE_DLG_MS05_X06_TUTORIAL_04', t, r)

        t = 'Benedict'
        r = units.getSwapUnitName(t)
        # self.common.replaceSubstring('TEXT_COMMON_BATTLE_UI_BATTLE_NAME_17_38', t, r)
        # self.common.replaceSubstring('TEXT_COMMON_THREE_SQUAD_BENEDICT', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_17_HUD_OPINION_MS17B_X35', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_17_OPINION_MS17B_X35', t, r)

        t = 'Frederica'
        r = units.getSwapUnitName(t)
        # self.common.replaceSubstring('TEXT_COMMON_BATTLE_UI_BATTLE_NAME_19_46', t, r)
        # self.common.replaceSubstring('TEXT_COMMON_THREE_SQUAD_FREDERICA', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_17_HUD_OPINION_MS17F_X37', t, r)
        self.common.replaceSubstring('TEXT_COMMON_VOTE_17_OPINION_MS17F_X37', t, r)

        # Replace all three
        string = self.common.text['TEXT_COMMON_VOTE_17_HUD_AGENDA']['Text'].string
        s1 = string.replace("Benedict's strategy", f"{units.getSwapUnitName('Benedict')}'s strategy")
        s2 = s1.replace("with Roland", f"with {units.getSwapUnitName('Roland')}")
        s3 = s2.replace("Frederica's vision", f"{units.getSwapUnitName('Frederica')}'s vision")
        self.common.text['TEXT_COMMON_VOTE_17_HUD_AGENDA']['Text'].string = s3
