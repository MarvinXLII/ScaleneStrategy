from Assets import Data
from Utility import get_filename


class Image:
    def __init__(self, pak, filename):
        self._data = Data(pak, filename)

    @property
    def data(self):
        return self._data.uasset.exports[1].uexp2

    @data.setter
    def data(self, data):
        self._data.uasset.exports[1].uexp2 = data

    def update(self):
        self._data.update(force=True)


class TitleImage(Image):
    def __init__(self, pak):
        super().__init__(pak, 'T_UI_Title_Menu_GameTitleLogo_BC.uasset')

    def updateTitle(self):
        with open(get_filename('image/title.dxt5'), 'rb') as file:
            pixels = bytearray(file.read())[0x81:]

        start = 0xf1 - 0x9c
        end = -0x18
        assert len(self.data[start:end]) == len(pixels)
        data = bytearray(self.data)
        data[start:end] = pixels
        self.data = data
