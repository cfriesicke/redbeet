# RedBeet: A console for the Focusrite Scarlett 6i6, 8i6, 18i6, 18i8, and 18i20.
#
# Copyright (C) 2015 Christian Friesicke <christian@friesicke.me>
#
# Based on proof-of-concept code [https://github.com/x42/scarlettmixer]
# Copyright (C) 2013 Robin Gareus <robin@gareus.org>
#
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.

import json
import math
import struct
import usb.core
import usb.util

# constants for auto-detection / identifying interfaces by usb product id
ID_AUTO = 0
ID_2I2 = 0x8006
ID_2I4 = 0x800a
ID_6I6 = 0x8012
ID_8I6 = 0x8002
ID_18I6 = 0x8000
ID_18I8 = 0x8014
ID_18I20 = 0x800c

# constants for set_impedance()
IMPEDANCE_LINE = 0x00
IMPEDANCE_INST = 0x01

# constants for set_pad()
PAD_OFF = 0x00
PAD_ON = 0x01

# constants for postroute_mute()
UNMUTE = 0x00
MUTE = 0x01


def _mixer_gain_to_hex(gain):
    """Calculate little endian byte sequence for matrix mixer element gain.

    Args:
        gain (float): Gain in dB; effective range [-128 .. 6].

    Returns:
        Little endian two-byte sequence of the gain's int representation;
        for use in USB control commands.

    """
    if gain < -128:
        gain = -128
    elif gain > 6:
        gain = 6
    value = int(math.floor(gain+.5))
    if value >= 0:
        return [0x00, 0x00 + value]
    else:
        return [0x00, (0x100 + value)]


def _postroute_gain_to_hex(gain):
    """Calculate little endian byte sequence for post-router gain.

    Args:
        gain (float): Gain in dB; effective range [-128 .. 0].

    Returns:
        Little endian two-byte sequence of the gain's int representation;
        for use in USB control commands.

    """
    if gain < -128:
        gain = -128
    if gain > 0:
        gain = 0
    # A 1dB step in gain equals a step of 256 in the integer representation.
    # Pack the resulting integer into a 16-bit signed struct and unpack as a
    # tuple of two signed bytes. The tuple order is little endian.
    byte_seq = struct.unpack('2b', struct.pack('1h', round(gain*256.0)))
    return byte_seq


def get_device_list():
    """Get list of usb device objects of all connected Scarlett devices."""
    device_list = list()
    for id_prod in [ID_2I2, ID_2I4, ID_6I6, ID_8I6, ID_18I6, ID_18I8, ID_18I20]:
        for device in usb.core.find(find_all=True, idVendor=0x1235, idProduct=id_prod):
            device_list.append(device)
    return device_list


# _____________________________________________________________________________


class Device:
    # constructor
    # @param device -- usb device object
    #
    # in the future add auto-detection, together with filtering multiple devices
    # by productid or serial number.
    def __init__(self, device=None):
        self.device = device

        # auto-detect (default: first found device)
        if self.device is None:
            self.device = get_device_list()[0]
            # auto-detect failed?
            if self.device is None:
                raise ValueError("No device found.")

        # before accessing the device, detach kernel drivers
        # store list of previously attached interfaces
        self.previously_attached = list()
        for interface in range(6):
            if self.device.is_kernel_driver_active(interface):
                self.previously_attached.append(interface)
                self.device.detach_kernel_driver(interface)

        # set bConfigurationValue=1
        self.device.set_configuration(1)

        # claim device interface 0 (control)
        usb.util.claim_interface(self.device, 0)

        # dictionary with pointers to json files that contain device-specific
        # configuration data
        # TODO: later files should be in /usr/share/package-foo/mapping/

        # TODO: delete 2i2, 2i4, or create correct json files
        json_file_by_id = {
            ID_2I2   : "mapping/scarlett_2i2_mapping_TODO.json",
            ID_2I4   : "mapping/scarlett_2i4_mapping_TODO.json",
            ID_18I6  : "mapping/scarlett_18i6_mapping.json",
            ID_8I6   : "mapping/scarlett_8i6_mapping.json",
            ID_18I20 : "mapping/scarlett_18i20_mapping_TODO.json",
            ID_6I6   : "mapping/scarlett_6i6_mapping.json",
            ID_18I8  : "mapping/scarlett_18i8_mapping.json"
        }
        # load json into dictionary with device configuration
        self.config = json.load(open(json_file_by_id[self.device.idProduct]))


    def __del__(self):
        # self.device might be None, e.g. when auto-detect failed
        if self.device:
            # release claimed interface; only then kernel can be re-attached
            usb.util.release_interface(self.device, 0)

            # finally, re-attach the kernel driver to the (previously attached)
            # interfaces. It is weird, but by attaching interface 0, interface 1
            # and 2 are attached automatically. The code below handles this by
            # calling is_kernel_driver_active() for every interface.
            for interface in self.previously_attached:
                if not self.device.is_kernel_driver_active(interface):
                    self.device.attach_kernel_driver(interface)


    def get_name(self):
        try:
            mfr = usb.util.get_string(self.device, self.device.iManufacturer)
            prod = usb.util.get_string(self.device, self.device.iProduct)
            ser = usb.util.get_string(self.device, self.device.iSerialNumber)
        except:
            print "USB error: get_string failed."
        name = "%s %s (S/N: %s)" % (mfr, prod, ser)
        return name

    # -------------------------------------------------------------------------
    # USB control transfers
    # -------------------------------------------------------------------------

    # The USB control transfers use only two request types:
    #   bmRequestType = 0x21 = host-to-device|class|interface -> "send"
    #   bmRequestType = 0xa1 = device-to-host|class|interface -> "receive"
    #
    # Overview of all "send"-type requests:
    #
    # bmRequest  wIndex  wValue          data      action
    #      0x01  0x0100  0x0900+channel  (2bytes)  Set analog input line/instr
    #                                              impedance
    #      0x01  0x0a00  0x0100+bus      (2bytes)  Mute/unmute output
    #      0x01  0x0b00  0x0100+channel  (2bytes)  Set analog input attenuation
    #      0x01  0x0a00  0x0200+bus      (2bytes)  Set output master volume
    #      0x01  0x2800  0x0100          (1byte)   Set clock source
    #      0x01  0x2900  0x0100          (4bytes)  Set sampling rate in Hz
    #      0x01  0x3200  0x0600+channel  (2bytes)  Assign source (=data) to
    #                                              mixer input channel
    #      0x01  0x3300  0x0000+bus      (2bytes)  Route mix (=data) to
    #                                              destination bus
    #      0x01  0x3400  ??                        Clear mixer -- force assignm.
    #                                              used during factory reset (?)
    #      0x01  0x3c00  0x0000+element  (2bytes)  Set matrix mixer gain (=data)
    #                                              for element
    #      0x03  0x3c00  0x005a          0xa5      Save settings to hardware
    #
    # Overview of all "receive"-type requests
    #
    # bmRequest  wIndex  wValue   action
    #      0x03  0x0000  0x3c00   Get peak meters of input channels
    #                             (len = 2 bytes x number of input channels)
    #      0x03  0x0001  0x3c00   Get peak meters of mixer channels
    #                             (len = 2 bytes x number of mixer channels)
    #      0x03  0x0003  0x3c00   Get peak meters of daw channels
    #                             (len = 2 bytes x number of daw channels)

    def usb_ctrl_send(self, bmRequest, wValue, wIndex, data):
        """Issue a send-type (host-to-device) USB control transfer."""
        try:
            assert self.device.ctrl_transfer(0x21, bmRequest, wValue, wIndex, data) == len(data)
        except:
            raise ValueError('USB control transfer failed')

    def usb_ctrl_recv(self, bmRequest, wValue, wIndex, data):
        "Issue a receive-type (device-to-host) USB control transfer."""
        try:
            rv = self.device.ctrl_transfer(0xa1, bmRequest, wValue, wIndex, data)
            return rv
        except:
            raise ValueError('USB control transfer failed')

    # ---- misc control--------------------------------------------------------

    # switch the impedance between line/mic and instrument
    def set_impedance(self, channel, impedance):
        if channel not in self.config["imp_switch"]:
            raise KeyError('Invalid input source for impedance switch')
        self.usb_ctrl_send(
            0x01,
            0x0900 + self.config["imp_switch"][channel],
            0x0100,
            [impedance, 0x00]
        )

    def set_pad(self, channel, pad_onoff):
        if channel not in self.config["pad_switch"]:
            raise KeyError('Invalid input source for pad switch')
        self.usb_ctrl_send(
            0x01,
            0x0b00 + self.config["pad_switch"][channel],
            0x0100,
            [pad_onoff, 0x00]
        )

    # set the clock source
    def set_clock_source(self, src):
        if src not in self.config["clk_switch"]:
            raise KeyError('Invalid clock source')
        self.usb_ctrl_send(
            0x01,
            0x0100,
            0x2800,
            [self.config["clk_switch"][src]]
        )

    # set sampling rate
    def set_sampling_rate(self, rate):
        # lazy little endian conversion by means of dictionary
        rate_dict = {
            44100 : [0x44, 0xac, 0x00, 0x00],
            48000 : [0x80, 0xbb, 0x00, 0x00],
            88200 : [0x88, 0x58, 0x01, 0x00],
            96000 : [0x00, 0x77, 0x01, 0x00]
        }
        if rate not in rate_dict:
            raise KeyError('Invalid sampling rate')
        self.usb_ctrl_send(0x01, 0x0100, 0x2900, rate_dict[rate])

    # save current config to be restored after power-cycles
    def save_settings_to_hardware(self):
        self.usb_ctrl_send(0x03, 0x005a, 0x3c00, [0xa5])


    # ---- mixer stage ---------------------------------------------------------

    # mixer stage: connect signal source to input of matrix mixer
    def set_mixer_source(self, src, mix_in):
        if src not in self.config["mixer_src"]:
            raise KeyError('Invalid signal source')
        if mix_in not in self.config["mixer_in"]:
            raise ValueError('Invalid matrix mixer input')
        self.usb_ctrl_send(
            0x01,
            0x0600 + self.config["mixer_in"][mix_in],
            0x3200,
            [self.config["mixer_src"][src], 0x00]
        )

    # mixer stage: set the gain of a matrix mixer element
    # @param mix_in -- number of matrix mixer input (0 .. mixer_input_num-1)
    # @param mix_out -- key of the dictionary mixer_output
    # @param gain -- element gain in dB (-infty .. +6 dB, default: 0 dB)
    def set_mixer_gain(self, mix_in, mix_out, gain=0):
        if mix_in not in self.config["mixer_in"]:
            raise ValueError('Invalid matrix mixer input')
        if mix_out not in self.config["mixer_out"]:
            raise KeyError('Invalid mixer output')
        element_index = (self.config["mixer_in"][mix_in] << 3) + (self.config["mixer_out"][mix_out] & 0x07)
        self.usb_ctrl_send(
            0x01,
            0x0100 + element_index,
            0x3c00,
            _mixer_gain_to_hex(gain)
        )


    # ____ routing stage ______________________________________________________

    def route_mix(self, src, dest):
        """Route a mix, a DAW channel or a hardware input to a hardware output.

        Args:
            src (string): Name of the source that is routed; must be defined in
                the device dictionary self.config["router_src"]. The source can
                be one of the hardware inputs of the device, one of the DAW
                channels, or one of the mixes from the device's matrix mixer.
            dest (string): Name of the destination to which the source is
                routed; must be defined in the device dictionary
                self.config["router_dest"].

        Raises:
            KeyError: An error occurred when trying to access invalid router
                sources or destinations.

        """
        if src not in self.config["router_src"]:
            raise KeyError('Invalid router source')
        if dest not in self.config["router_dest"]:
            raise KeyError('Invalid router destination')
        self.usb_ctrl_send(
            0x01,
            self.config["router_dest"][dest],
            0x3300,
            [self.config["router_src"][src], 0x00]
        )


    # ____ post-routing stage _________________________________________________

    def set_postroute_mute(self, bus, mute):
        """Mute or unmute one of the output buses in the post-routing stage.

        Args:
            bus (string): Name of the output bus; must be defined in the device
                dictionary self.config["signal_out"].
            mute (int): Enum-like int value defined in the scarlett module;
                must be MUTE or UNMUTE.

        Raises:
            KeyError: An error occurred when trying to access an invalid output
                bus.

        """
        if bus not in self.config["signal_out"]:
            raise KeyError('Invalid output bus')
        self.usb_ctrl_send(
            0x01,
            0x0100 + self.config["signal_out"][bus],
            0x0a00,
            [mute, 0x00]
        )

    def set_postroute_gain(self, bus, gain):
        """Set the gain of an output bus in the post-routing stage.

        Args:
            bus (string): Name of the output bus; must be defined in the device
                dictionary self.config["signal_out"].
            gain (float): Gain of the ouput bus in dB. Values are truncated to
                the interval [-128 .. 0]. Since the gain is negative or zero,
                the bus is actually attenuated, not amplified.

        Raises:
            KeyError: An error occurred when trying to access an invalid output
                bus.

        """
        if bus not in self.config["signal_out"]:
            raise KeyError('Invalid output bus')
        self.usb_ctrl_send(
            0x01,
            0x0200 + self.config["signal_out"][bus],
            0x0a00, _postroute_gain_to_hex(gain)
        )
