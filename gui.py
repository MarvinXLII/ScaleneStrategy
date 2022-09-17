import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from release import RELEASE
import hjson
import random
import os
import shutil
import glob
import sys
sys.path.append('src')
from Utility import get_filename
from Randomizer import Switch
from Pak import Pak

MAIN_TITLE = f"Scalene Strategy v{RELEASE}"

# Source: https://www.daniweb.com/programming/software-development/code/484591/a-tooltip-class-for-tkinter
class CreateToolTip(object):
    '''
    create a tooltip for a given widget
    '''
    def __init__(self, widget, text='widget info', wraplength=200, dx=25, dy=25):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.close)
        self.wraplength = wraplength
        self.dx = dx
        self.dy = dy

    def enter(self, event=None):
        x = y = 0
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + self.dx
        y += self.widget.winfo_rooty() + self.dy
        # creates a toplevel window
        self.tw = tk.Toplevel(self.widget)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(self.tw, text=self.text, justify='left',
                      background='white', relief='solid', borderwidth=1,
                      wraplength=self.wraplength,
                      font=("times", "12", "normal"),
                      padx=4, pady=6,
        )
        label.pack(ipadx=1)

    def close(self, event=None):
        self.tw.destroy()

        # if self.tw:
        #     self.tw.destroy()


class GuiApplication:
    def __init__(self, settings=None):
        self.master = tk.Tk()
        self.master.geometry('670x530')
        self.master.title(MAIN_TITLE)
        self.initialize_gui()
        self.initialize_settings(settings)
        self.master.mainloop()


    def initialize_gui(self):

        self.warnings = []
        self.togglers = []
        self.settings = {}
        self.settings['release'] = tk.StringVar()
        self.pak = None

        with open(get_filename('json/gui.json'), 'r') as file:
            fields = hjson.loads(file.read())

        #####################
        # PAKS FOLDER STUFF #
        #####################

        labelfonts = ('Helvetica', 14, 'bold')
        lf = tk.LabelFrame(self.master, text='Pak File', font=labelfonts)
        lf.grid(row=0, columnspan=2, sticky='nsew', padx=5, pady=5, ipadx=5, ipady=5)

        # Path to paks
        self.settings['pak'] = tk.StringVar()
        self.settings['pak'].set('')

        pakFilename = tk.Entry(lf, textvariable=self.settings['pak'], width=65, state='readonly')
        pakFilename.grid(row=0, column=0, columnspan=2, padx=(10,0), pady=3)

        pakLabel = tk.Label(lf)#, text='Pak file')
        pakLabel.grid(row=1, column=0, sticky='w', padx=5, pady=2)

        pakButton = tk.Button(lf, text='Browse ...', command=self.getPakFile, width=20) # needs command..
        pakButton.grid(row=1, column=1, sticky='e', padx=5, pady=2)
        self.buildToolTip(pakButton,
                          """
Input the game's file "Newera-Switch.pak".\n
This randomizer is only compatible with the Switch release v1.0.3.
                          """
                          , wraplength=500)

        #####################
        # SEED & RANDOMIZER #
        #####################

        lf = tk.LabelFrame(self.master, text="Seed", font=labelfonts)
        lf.grid(row=0, column=2, columnspan=2, sticky='nsew', padx=5, pady=5, ipadx=5, ipady=5)
        self.settings['seed'] = tk.IntVar()
        self.randomSeed()

        box = tk.Spinbox(lf, from_=0, to=1e8, width=9, textvariable=self.settings['seed'])
        box.grid(row=2, column=0, sticky='e', padx=60)

        seedBtn = tk.Button(lf, text='Random Seed', command=self.randomSeed, width=12, height=1)
        seedBtn.grid(row=3, column=0, columnspan=1, sticky='we', padx=30, ipadx=30)

        self.randomizeBtn = tk.Button(lf, text='Randomize', command=self.randomize, height=1)
        self.randomizeBtn.grid(row=4, column=0, columnspan=1, sticky='we', padx=30, ipadx=30)

        ############
        # SETTINGS #
        ############

        # Tabs setup
        tabControl = ttk.Notebook(self.master)
        tabNames = ['Settings']
        tabs = {name: ttk.Frame(tabControl) for name in tabNames}
        for name, tab in tabs.items():
            tabControl.add(tab, text=name)
        tabControl.grid(row=2, column=0, columnspan=20, sticky='news')

        # Tab label
        for name, tab in tabs.items():
            labelDict = fields[name]
            for i, (key, value) in enumerate(labelDict.items()):
                row = i % 3
                column = i // 3
                # Setup LabelFrame
                lf = tk.LabelFrame(tab, text=key, font=labelfonts)
                lf.grid(row=row, column=column, padx=10, pady=5, ipadx=30, ipady=5, sticky='news')
                # Dictionary of buttons for toggling
                buttonDict = {}
                # Loop over buttons
                row = 0
                for vj in value:
                    name = vj['name']

                    if vj['type'] == 'checkbutton':
                        self.settings[name] = tk.BooleanVar()
                        buttons = []
                        toggleFunction = self.toggler(buttons, name)
                        if 'toggle' in vj:
                            button = ttk.Checkbutton(lf, text=vj['label'], variable=self.settings[name], command=toggleFunction, state=tk.DISABLED)
                        else:
                            button = ttk.Checkbutton(lf, text=vj['label'], variable=self.settings[name], command=toggleFunction)
                        button.grid(row=row, padx=10, sticky='we')
                        self.buildToolTip(button, vj)
                        buttonDict[name] = buttons
                        if 'toggle' in vj:
                            buttonDict[vj['toggle']].append((self.settings[vj['name']], button))
                        row += 1
                        if 'indent' in vj:
                            self.togglers.append(toggleFunction)
                            for vk in vj['indent']:
                                self.settings[vk['name']] = tk.BooleanVar()
                                button = ttk.Checkbutton(lf, text=vk['label'], variable=self.settings[vk['name']], state=tk.DISABLED)
                                button.grid(row=row, padx=30, sticky='w')
                                self.buildToolTip(button, vk)
                                buttons.append((self.settings[vk['name']], button))
                                if 'toggle' in vk:
                                    buttonDict[vk['toggle']].append((self.settings[vk['name']], button))
                                row += 1

                    elif vj['type'] == 'spinbox':
                        text = f"{vj['label']}:".ljust(20, ' ')
                        ttk.Label(lf, text=text).grid(row=row, column=0, padx=10, sticky='w')
                        spinbox = vj['spinbox']
                        self.settings[name] = tk.IntVar()
                        self.settings[name].set(spinbox['default'])
                        box = tk.Spinbox(lf, from_=spinbox['min'], to=spinbox['max'], width=3, textvariable=self.settings[name], state='readonly')
                        box.grid(row=row, column=1, padx=0, sticky='w')
                        self.buildToolTip(box, vj)
                        row += 1

                    elif vj['type'] == 'radiobutton':
                        self.settings[name] = tk.BooleanVar()
                        buttons = []
                        toggleFunction = self.toggler(buttons, name)
                        button = ttk.Checkbutton(lf, text=vj['label'], variable=self.settings[name], command=toggleFunction)
                        button.grid(row=row, padx=10, sticky='w')
                        self.buildToolTip(button, vj)
                        self.togglers.append(toggleFunction)
                        row += 1
                        keyoption = name+'-option'
                        self.settings[keyoption] = tk.StringVar()
                        self.settings[keyoption].set(None)
                        for ri in vj['indent']:
                            radio = tk.Radiobutton(lf, text=ri['label'], variable=self.settings[keyoption], value=ri['value'], padx=15, state=tk.DISABLED)
                            radio.grid(row=row, column=0, padx=14, sticky='w')
                            self.buildToolTip(radio, ri)
                            buttons.append((self.settings[keyoption], radio))
                            row += 1

        # For warnings/text at the bottom
        self.canvas = tk.Canvas()
        self.canvas.grid(row=6, column=0, columnspan=20, pady=10)

    def getPakFile(self):
        pakFile = filedialog.askopenfilename()
        if pakFile:
            self.loadPakFile(pakFile)

    def loadPakFile(self, pakFile):
        self.clearBottomLabels()
        if os.path.isfile(pakFile):
            self.bottomLabel('Loading Pak....', 'blue', 0)
            try:
                self.pak = Pak(pakFile)
            except:
                self.clearBottomLabels()
                self.bottomLabel('This file is incompatible with the randomizer.','red',0)
                return False
        else:
            self.settings['pak'].set('')
            self.bottomLabel('Load a pak file', 'red', 0)
            self.bottomLabel('', 'red', 2)
            return False

        if self.pak.shaIndex == int('0x26fe91d322ceaa90b9a3e6a6c1ad95f0a976299d', 0).to_bytes(20, byteorder='big'):
            self.bottomLabel('Done', 'blue', 1)
            self.settings['pak'].set(pakFile)
            return True

        self.clearBottomLabels()
        if self.pak.shaIndex == int('0xf97dad07a9dd97729d0af06d3c47e14266ea7a96', 0).to_bytes(20, byteorder='big'):
            self.bottomLabel('This pak file is for the Switch release v1.0.2 game.','red',0)
            self.bottomLabel('The randomizer is only compatible with release v1.0.3.','red',1)
        else:
            self.bottomLabel('This pak file is incompatible with the randomizer.','red',0)
        return False
        
    def toggler(self, lst, key):
        def f():
            if self.settings[key].get():
                try: # "if radiobutton"
                    lst[0][1].select() # Selects the first option
                except (AttributeError, IndexError) as error:
                    pass
                for vi, bi in lst:
                    bi.config(state=tk.NORMAL)
            else:
                for vi, bi in lst:
                    if isinstance(vi.get(), bool):
                        vi.set(False)
                    if isinstance(vi.get(), str):
                        vi.set(None)
                    bi.config(state=tk.DISABLED)
            return key, lst
        return f

    def buildToolTip(self, button, field, wraplength=200):
        if isinstance(field, str):
            CreateToolTip(button, field, wraplength, dx=25, dy=35)
        if isinstance(field, dict):
            if 'help' in field:
                CreateToolTip(button, field['help'])

    def turnBoolsOff(self):
        for si in self.settings.values():
            if isinstance(si.get(), bool):
                si.set(False)
            
    def initialize_settings(self, settings):
        self.settings['release'].set(RELEASE)
        if settings is None:
            self.turnBoolsOff()
            return
        for key, value in settings.items():
            if key == 'pak':
                loaded = self.loadPakFile(value)
                if not loaded:
                    self.clearBottomLabels()
                continue
            if key == 'release':
                continue
            if key not in self.settings:
                continue
            self.settings[key].set(value)
        for toggle in self.togglers:
            key, buttons = toggle()
            keyOption = f'{key}-option'
            # Set the correct option for radio buttons
            if settings[key] and keyOption in settings:
                for option, button in buttons:
                    button.select()
                    if self.settings[keyOption] == settings[keyOption]:
                        break

    def bottomLabel(self, text, fg, row):
        L = tk.Label(self.canvas, text=text, fg=fg)
        L.grid(row=row, columnspan=20)
        self.warnings.append(L)
        self.master.update()

    def clearBottomLabels(self):
        while self.warnings != []:
            warning = self.warnings.pop()
            warning.destroy()
        self.master.update()
        
    def randomSeed(self):
        self.settings['seed'].set(random.randint(0, 99999999))

    def randomize(self):
        if self.settings['pak'].get() == '':
            self.clearBottomLabels()
            self.bottomLabel('Must load an appropriate pak file.', 'red', 0)
            return

        settings = { key: value.get() for key, value in self.settings.items() }

        self.clearBottomLabels()
        self.bottomLabel('Randomizing....', 'blue', 0)

        if randomize(self.pak, settings):
            self.clearBottomLabels()
            self.bottomLabel('Randomizing...done! Good luck!', 'blue', 0)
        else:
            self.clearBottomLabels()
            self.bottomLabel('Randomizing failed.', 'red', 0)


def randomize(pak, settings):
    try:
        pak.clean()
        mod = Switch(pak, settings)
        mod.randomize()
        mod.qualityOfLife()
        mod.dump()
        return True
    except:
        mod.failed()
        return False


if __name__ == '__main__':
    settingsFile = None
    if len(sys.argv) > 2:
        print('Usage: python gui.py <settings.json>')
    elif len(sys.argv) == 2:
        settingsFile = sys.argv[1]
    else:
        if os.path.isfile('settings.json'):
            settingsFile = 'settings.json'

    exePath = os.path.dirname(sys.argv[0])
    if exePath:
        os.chdir(exePath)

    if settingsFile:
        with open(settingsFile, 'r') as file:
            settings = hjson.load(file)
        GuiApplication(settings)
    else:
        GuiApplication()
