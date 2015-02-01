#!/usr/bin/python2
"""Demo code for the ScarlettDevice class.

Copyright (C) 2015 Christian Friesicke <christian@friesicke.me>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2, or (at your option)
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""


import sys
import scarlett
import time


def main():
    """Main function with all the demo code."""

    try:
        sdev = scarlett.ScarlettDevice()  # try auto-detect
    except ValueError:
        print "No Scarlett device found. \
               Is your device switched on and connected to USB?"
        return -1

    print "Found device: %s" % sdev.get_name()

    # some blinkenlights demo code for the 18i8

    sdev.set_impedance("ANALOG1", scarlett.IMPEDANCE_LINE)
    sdev.set_impedance("ANALOG2", scarlett.IMPEDANCE_LINE)
    time.sleep(0.2)
    sdev.set_impedance("ANALOG1", scarlett.IMPEDANCE_INST)
    sdev.set_impedance("ANALOG2", scarlett.IMPEDANCE_INST)

    sdev.set_pad("ANALOG1", scarlett.PAD_OFF)
    sdev.set_pad("ANALOG2", scarlett.PAD_OFF)
    sdev.set_pad("ANALOG3", scarlett.PAD_OFF)
    sdev.set_pad("ANALOG4", scarlett.PAD_OFF)
    time.sleep(0.2)
    sdev.set_pad("ANALOG1", scarlett.PAD_ON)
    time.sleep(0.2)
    sdev.set_pad("ANALOG2", scarlett.PAD_ON)
    time.sleep(0.2)
    sdev.set_pad("ANALOG3", scarlett.PAD_ON)
    time.sleep(0.2)
    sdev.set_pad("ANALOG4", scarlett.PAD_ON)
    time.sleep(0.2)
    sdev.set_pad("ANALOG4", scarlett.PAD_OFF)
    time.sleep(0.2)
    sdev.set_pad("ANALOG3", scarlett.PAD_OFF)
    time.sleep(0.2)
    sdev.set_pad("ANALOG2", scarlett.PAD_OFF)
    time.sleep(0.2)
    sdev.set_pad("ANALOG1", scarlett.PAD_OFF)

    # here comes the serious part

    # set clock source and sampling frequency
    sdev.set_clock_source("INTERNAL")
    sdev.set_sampling_rate(96000)

    # disconnect all mixer inputs
    for mixer_in_key in sdev.config["mixer_in"].keys():
        sdev.set_mixer_source("OFF", mixer_in_key)

    # set all matrix mixer elements to -infty dB
    for mixer_in_key in sdev.config["mixer_in"].keys():
        for mixer_out_key in sdev.config["mixer_out"].keys():
            sdev.set_mixer_gain(mixer_in_key, mixer_out_key, float("-inf"))

    # connect some analog sources
    sdev.set_mixer_source("ANALOG1", "CH_01")
    sdev.set_mixer_source("ANALOG2", "CH_02")
    sdev.set_mixer_source("ANALOG3", "CH_03")
    sdev.set_mixer_source("ANALOG4", "CH_04")

    # ch1 and ch2 as centered stereo mix1/2 at 0dB
    sdev.set_mixer_gain("CH_01", "MIX1", 0)
    sdev.set_mixer_gain("CH_01", "MIX2", 0)
    sdev.set_mixer_gain("CH_02", "MIX1", 0)
    sdev.set_mixer_gain("CH_02", "MIX2", 0)

    # ch3 and ch4 as mono mixes at -3 dB
    sdev.set_mixer_gain("CH_03", "MIX3", -3)
    sdev.set_mixer_gain("CH_04", "MIX4", -3)

    # route stereo mix1/2 to HP01
    sdev.route_mix("MIX1", "PHONES1_L")
    sdev.route_mix("MIX2", "PHONES1_R")

    # route mono mix 3 to left monitor
    sdev.route_mix("MIX3", "MONITOR_L")

    # route mono mix 4 to right HP02
    sdev.route_mix("MIX4", "PHONES2_R")

    # save permanently
    sdev.save_settings_to_hardware()


if __name__ == "__main__":
    sys.exit(main())
