import os
import hjson
import sys
sys.path.append('src')
import random
import argparse
from Randomizer import Switch
from Pak import Pak
from release import RELEASE

def argumentParser():
    parser = argparse.ArgumentParser(description='Randomize Triangle Strategy')
    parser.add_argument('--seed', dest='seed', default=None, type=int, help='Seed for the random number generator')
    parser.add_argument('settings', default=None, nargs='?', help='Provide settings in a file')
    parser.add_argument('--pakFile', dest='pak', default=None, help='Pak file for the game')
    parser.add_argument('--testing', dest='testing', default=None, action='store_const', const=True, help='Testing for development purposes')
    args = parser.parse_args()
    return {k:v for k, v in vars(args).items() if v is not None}


def main():
    args = argumentParser()

    if 'settings' in args and os.path.isfile(args['settings']):
        with open(args['settings'], 'r') as file:
            settings = hjson.load(file)
    else:
        settings = {
            'pak': 'Newera-Switch.pak',
            'seed': random.randint(0, 2**31-1),
            'random-class-support-skills': True,
            'shuffle-class-rank-items': True,
            'random-weapon-materials': True,
            'random-weapon-exclusives': True,
            'random-weapon-preconditions': True,
            'random-item-costs': True,
            'random-inventory-numbers': True,
            'qol-easier-voting': True,
            'qol-serenoa-optional': True,
            'random-battle-unit-placement': True,
            'shuffle-battle-initial-charge-times': True,
            'shuffle-battle-weather': True,
            'shuffle-battle-time': True,
            'shuffle-playable-units': True,
            'update-playable-unit-sprites': True,
            'random-exploration-items': True,
            # 'testing': True,
        }

    for k, v in args.items():
        settings[k] = v
    settings['release'] = RELEASE

    if os.path.isfile(settings['pak']):
        pak = Pak(settings['pak'])
    else:
        sys.exit(f"Pak file {settings['pak']} does not exist!")

    mod = Switch(pak, settings)
    mod.randomize()
    mod.qualityOfLife()
    mod.dump()


if __name__ == '__main__':
    main()
