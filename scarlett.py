"""A module to control USB devices of the Focusrite Scarlett series.

This module contains the ScarlettDevice class and further helper functions with
which Focusrite Scarlett devices can be controlled. The class supports the 6i6,
8i6, 18i6, 18i8, and 18i20 devices. The 2i2 and 2i4 devices are not supported;
they are controlled only by knobs on the front panel.

Copyright (C) 2015 Christian Friesicke <christian@friesicke.me>

Based on proof-of-concept code [https://github.com/x42/scarlettmixer]
Copyright (C) 2013 Robin Gareus <robin@gareus.org>

License: GPL3 [http://www.gnu.org/licenses/gpl.html]
"""

import json
import math
import struct
import usb.core
import usb.util


# constants for auto-detecting interfaces by usb product id
ID_AUTO = 0
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


# constants for set_postroute_mute()
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
    # A 1dB step in gain equals a step of 256 in the integer representation.
    # Pack integer as signed short, unpack as two signed bytes (lsb, msb).
    byte_seq = list(struct.unpack('2b', struct.pack('1h', round(gain*256.0))))
    return byte_seq

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
    # Pack integer as signed short, unpack as two signed bytes (lsb, msb).
    byte_seq = list(struct.unpack('2b', struct.pack('1h', round(gain*256.0))))
    return byte_seq


def _twobyte_to_db(lsb, msb):
    """Calculate peak level in dB from a two-byte sequence.

    Args:
        byte_lo, byte_hi (int): lsb and msb of the two byte sequence.

    Returns:
        Peak level in dB; range is [-inf: 0].

    """
    # Pack two bytes (little endian) into struct; unpack as 16-bit int.
    two_int8_bytes = struct.pack('2B', lsb & 0xff, msb & 0xff)
    int16_value = list(struct.unpack('1H', two_int8_bytes))[0]
    if int16_value == 0:
        return float('-inf')  # otherwise log10 would raise an exception
    else:
        return 20*math.log10(int16_value/65536.0)


def get_device_list():
    """Get a list of all connected Scarlett devices.

    Returns:
        List of pyusb device objects of all connected Scarlett devices.

    """
    device_list = list()
    for id_prod in [ID_6I6, ID_8I6, ID_18I6, ID_18I8, ID_18I20]:
        for device in usb.core.find(find_all=True, idVendor=0x1235,
                                    idProduct=id_prod):
            device_list.append(device)
    return device_list


def get_device_name(device):
    """Get a human-readable and unique name of a Scarlett device.

    Args:
        device (usb.core.Device): usb object associated with Scarlett device.

    Returns:
        A string consisting of manufacturer name (Focusrite), product name,
        and the serial number of the device. Because of the serial number, the
        returned string can be used as a unique identifier of the device.

    """
    mfr = usb.util.get_string(device, device.iManufacturer)
    prod = usb.util.get_string(device, device.iProduct)
    ser = usb.util.get_string(device, device.iSerialNumber)
    name = "%s %s (S/N: %s)" % (mfr, prod, ser)
    return name

# _____________________________________________________________________________


class ScarlettDevice(object):
    """A class to control USB devices of the Focusrite Scarlett series.

    The class can control the hardware mixer, router, and other features such
    as setting input impedance, input attenuation, clock source, and master
    volume/mute. Furthermore, peak meter levels can be read from individual
    channels.

    """

    def __init__(self, device=None):
        """Construct a new ScarlettDevice instance.

        Args:
            device (usb.core.Device): usb object to be controlled by the
                instance. The default value is None, which triggers the auto-
                detection. Auto-detection gathers a list of all valid Scarlett
                devices attached to USB and picks the first item of the list.

        Raises:
            ValueError: An error occured when auto-detect does not find any
                valid Scarlett device attached to USB.

        TODO: add auto-detection together with filtering multiple present
            devices by productid or serial number.
        """
        self.device = device

        # auto-detect (default: first found device)
        if self.device is None:
            device_list = get_device_list()
            if not device_list:  # empty list; auto-detect failed?
                raise ValueError("No device found.")
            else:
                self.device = device_list[0]

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
        # TODO: create 18i20 json file
        json_file_by_id = {
            ID_6I6:   "mapping/scarlett_6i6_mapping.json",
            ID_8I6:   "mapping/scarlett_8i6_mapping.json",
            ID_18I6:  "mapping/scarlett_18i6_mapping.json",
            ID_18I8:  "mapping/scarlett_18i8_mapping.json",
            ID_18I20: "mapping/scarlett_18i20_mapping_TODO.json"
        }
        # load json into dictionary with device configuration
        self.config = json.load(open(json_file_by_id[self.device.idProduct]))

    def __del__(self):
        # self.device might be None, e.g. when auto-detect failed
        if self.device:
            # release claimed interface; only then kernel can be re-attached
            usb.util.release_interface(self.device, 0)

            # finally, re-attach the kernel driver to the (previously attached)
            # interfaces. It is weird, but by attaching interface 0,
            # interfaces 1 and 2 are attached automatically. The code below
            # handles this by calling is_kernel_driver_active() for every
            # interface.
            for interface in self.previously_attached:
                if not self.device.is_kernel_driver_active(interface):
                    self.device.attach_kernel_driver(interface)

    def get_name(self):
        """Get the name and serial number of the Scarlett device."""
        return get_device_name(self.device)

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
    #      0x01  0x3200  0x0600+channel  (2bytes)  Assign source to mixer input
    #                                              channel
    #      0x01  0x3300  0x0000+bus      (2bytes)  Route mix to destination
    #                                              bus
    #      0x01  0x3400  ??                        Clear mixer -- force assign.
    #                                              used during factory reset ?
    #      0x01  0x3c00  0x0000+element  (2bytes)  Set matrix mixer gain for
    #                                              element
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

    def usb_ctrl_send(self, bm_request, w_value, w_index, data):
        """Issue a send-type (host-to-device) USB control transfer."""
        try:
            assert self.device.ctrl_transfer(0x21, bm_request, w_value,
                                             w_index, data) == len(data)
        except:
            raise ValueError('USB control transfer failed')

    def usb_ctrl_recv(self, bm_request, w_value, w_index, data):
        "Issue a receive-type (device-to-host) USB control transfer."""
        try:
            received_data = self.device.ctrl_transfer(0xa1, bm_request,
                                                      w_value, w_index, data)
            return received_data
        except:
            raise ValueError('USB control transfer failed')

    # ____ misc control _______________________________________________________

    def set_impedance(self, channel, impedance):
        """Switch the impedance level of an analog hardware input.

        The impedance can be switched between "line/mic" and "instrument". The
        choice of line or mic further depends on the connector type that is
        plugged into the input (TRS = line, XLR = mic).

        Args:
            channel (string): Name of the analog input for which the impedance
                level is to be set; must be defined in the device dictionary
                self.config["imp_switch"].
            impedance (int): Enum-like int value defined in the scarlett
                module; must be IMPEDANCE_LINE or IMPEDANCE_INST.

        Raises:
            KeyError: An error occurred when trying to set the impedance of an
                invalid hardware input.

        """
        if channel not in self.config["imp_switch"]:
            raise KeyError('Invalid input source for impedance switch')
        self.usb_ctrl_send(
            0x01,
            0x0900 + self.config["imp_switch"][channel],
            0x0100,
            [impedance, 0x00]
        )

    def set_pad(self, channel, pad_onoff):
        """Set pad (attenuation) of analog hardware inputs.

        The attenuation level itself cannot be set with this command. It is a
        fixed level reduction typically used when connecting sources that are
        too "hot" and that would otherwise distort the input pre-amp.

        Args:
            channel (string): Name of the analog input to attenuate; must be
                defined in the device dictionary self.config["pad_switch"].
            pad_onoff (int): Enum-like int value defined in the scarlett
                module; must be PAD_ON or PAD_OFF.

        Raises:
            KeyError: An error occured when trying to set the pad of an invalid
                hardware input.

        """
        if channel not in self.config["pad_switch"]:
            raise KeyError('Invalid input source for pad switch')
        self.usb_ctrl_send(
            0x01,
            0x0b00 + self.config["pad_switch"][channel],
            0x0100,
            [pad_onoff, 0x00]
        )

    def set_clock_source(self, src):
        """Set the hardware clock source.

        Args:
            src (string): Name of the hardware clock source; must be defined in
                the device dictionary self.config["clk_switch"].

        Raises:
            KeyError: An error occured when trying to set an invalid hardware
                clock source.

        """
        if src not in self.config["clk_switch"]:
            raise KeyError('Invalid clock source')
        self.usb_ctrl_send(
            0x01,
            0x0100,
            0x2800,
            [self.config["clk_switch"][src]]
        )

    def set_sampling_rate(self, rate):
        """Set sampling rate.

        Args:
            rate (int): sampling rate in Hz. The only allowed values are
            44100, 48000, 8820, and 96000.

        Raises:
            ValueError: An error occurred when trying to set an invalid rate.

        """
        if rate not in [44100, 48000, 88200, 96000]:
            raise ValueError('Invalid sampling rate')
        # pack rate in int, unpack as 4-byte tuple, then convert to list.
        rate_seq = list(struct.unpack('4b', struct.pack('i', rate)))
        self.usb_ctrl_send(0x01, 0x0100, 0x2900, rate_seq)

    def save_settings_to_hardware(self):
        """Save configuration to device; restored after power-cycles."""
        self.usb_ctrl_send(0x03, 0x005a, 0x3c00, [0xa5])

    def zero_settings():
        """Disconnect all inputs and outputs; set all gains to 0 dB."""

        # disconnect all matrix mixer inputs; set all matrix mixer elements to
        # unity gain (0 dB).
        for mixer_in in self.device.config["mixer_in"]:
            self.set_mixer_source("OFF", mixer_in)
            for mixer_out in self.device.config["mixer_out"]:
                mixer_set_gain(mixer_in, mixer_out, 0)

        # disconnect all router inputs
        for dest in self.device.config["router_dest"]:
            self.route_mix("OFF", dest)

        # unmute and set all master buses to unity gain (0 dB)
        for bus in self.device.config["signal_out"]:
            self.set_postroute_mute(bus, UNMUTE)
            self.set_postroute_gain(bus, 0)


    # ____ mixer stage ________________________________________________________

    def set_mixer_source(self, src, mix_in):
        """Connect a signal source to a matrix mixer input.

        Args:
            src (string): Name of the source that is connected to the matrix
                mixer input; must be defined in the device dictionary
                self.config["mixer_src"]. The source can be one of the hardware
                inputs of the device or one of the DAW channels.
            mix_in (string): Name of the matrix mixer input; must be defined in
                the device dictionary self.config["mixer_in"].

        Raises:
            KeyError: An error occurred when trying to access invalid signal
                sources or matrix mixer inputs.

        """
        if src not in self.config["mixer_src"]:
            raise KeyError('Invalid signal source')
        if mix_in not in self.config["mixer_in"]:
            raise KeyError('Invalid matrix mixer input')
        self.usb_ctrl_send(
            0x01,
            0x0600 + self.config["mixer_in"][mix_in],
            0x3200,
            [self.config["mixer_src"][src], 0x00]
        )

    def set_mixer_gain(self, mix_in, mix_out, gain=0):
        """Set the gain of a matrix mixer element.

        Args:
            mix_in (string): Name of the matrix mixer input; must be defined in
                the device dictionary self.config["mixer_in"].
            mix_out (string): Name of the matrix mixer output; must be defined
                in the device dictionary self.config["mixer_in"].
            gain (float): Gain of the matrix mixer element in dB. Values will
                be truncated to the interval [-128 .. +6]. The default value
                is 0 dB.
        Raises:
            KeyError: An error occurred when trying to access invalid matrix
                mixer input or output.

        """
        if mix_in not in self.config["mixer_in"]:
            raise KeyError('Invalid matrix mixer input')
        if mix_out not in self.config["mixer_out"]:
            raise KeyError('Invalid mixer output')
        element_index = ((self.config["mixer_in"][mix_in] << 3) +
                         (self.config["mixer_out"][mix_out] & 0x07))
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
            gain (float): Gain of the ouput bus in dB. Values will be truncated
                to the interval [-128 .. 0]. Since the gain is not positive,
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

    # ____ peak meters ________________________________________________________

    def get_peak_meters(self):
        """Get all peak meter levels.

        Returns:
            Dictionary of peak meter levels in dB for all {'input', 'daw',
            and 'mix'} channels.

        """

        # TODO: this only holds for the 18i8 -- should be put in self.config[]
        num_inp_ch = 18
        num_daw_ch = 8
        num_mix_ch = 8
        inp_data = self.usb_ctrl_recv(0x03, 0x0000, 0x3c00, 2*num_inp_ch)
        daw_data = self.usb_ctrl_recv(0x03, 0x0003, 0x3c00, 2*num_daw_ch)
        mix_data = self.usb_ctrl_recv(0x03, 0x0001, 0x3c00, 2*num_mix_ch)

        inp_db = list()
        daw_db = list()
        mix_db = list()
        for channel in range(num_inp_ch):
            inp_db.append(_twobyte_to_db(inp_data[2*channel],
                                         inp_data[2*channel+1]))
        for channel in range(num_daw_ch):
            daw_db.append(_twobyte_to_db(daw_data[2*channel],
                                         daw_data[2*channel+1]))
        for channel in range(num_mix_ch):
            mix_db.append(_twobyte_to_db(mix_data[2*channel],
                                         mix_data[2*channel+1]))
        return {'input': inp_db, 'daw': daw_db, 'mix': mix_db}
