#!/usr/bin/env python

from gi.repository import Gtk
import scarlett


# _____________________________________________________________________________


class RedBeetWindow(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self, title="RedBeet")
        self.set_border_width(10)
        self.set_default_size(400, 600)

        self.hb = Gtk.HeaderBar()
        self.hb.set_show_close_button(True)
        self.hb.props.title = "RedBeet"
        self.hb.props.subtitle = "Mix1 (inactive)"
        self.set_titlebar(self.hb)

        # instance variables
        self.device = scarlett.Device()
        self.notebook = Gtk.Notebook()

        # router notebook
        router_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

        # route mixes/sources to destination
        dest_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        for dest in sorted(self.device.config["router_dest"].keys()):
            dest_label = Gtk.Label.new(dest)
            src_combo = Gtk.ComboBoxText()
            for src in sorted(self.device.config["router_src"].keys()):
                src_combo.append(id=src, text=src)
            src_combo.set_active_id("OFF")
            src_combo.set_wrap_width(4)
            src_combo.connect("changed", self.on_src_combo_changed, dest)
            dest_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
            dest_vbox.pack_start(dest_label, False, False, 5)
            dest_vbox.pack_start(src_combo, False, False, 5)
            dest_hbox.pack_start(dest_vbox, False, False, 5)
        dest_frame = Gtk.Frame.new("Router Destinations")
        dest_frame.add(dest_hbox)

        # impedance switches
        imp_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        for imp in sorted(self.device.config["imp_switch"].keys()):
            imp_label = Gtk.Label.new(imp)
            imp_button = Gtk.ToggleButton.new_with_label("LINE/MIC")
            imp_button.connect("toggled", self.on_impedance_toggled, imp)
            imp_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
            imp_vbox.pack_start(imp_label, False, False, 5)
            imp_vbox.pack_start(imp_button, False, False, 5)
            imp_hbox.pack_start(imp_vbox, False, False, 5)
        imp_frame = Gtk.Frame.new("Impedance Level")
        imp_frame.add(imp_hbox)

        # pad/attenuation switches
        pad_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        for pad in sorted(self.device.config["pad_switch"].keys()):
            pad_label = Gtk.Label.new(pad)
            pad_button = Gtk.ToggleButton.new_with_label("OFF")
            pad_button.connect("toggled", self.on_pad_toggled, pad)
            pad_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
            pad_vbox.pack_start(pad_label, False, False, 5)
            pad_vbox.pack_start(pad_button, False, False, 5)
            pad_hbox.pack_start(pad_vbox, False, False, 5)
        pad_frame = Gtk.Frame.new("Attenuation")
        pad_frame.add(pad_hbox)

        # todo
        clk_frame = Gtk.Frame.new("Clock Source")

        router_vbox.pack_start(dest_frame, False, False, 5)
        router_vbox.pack_start(imp_frame, False, False, 5)
        router_vbox.pack_start(pad_frame, False, False, 5)

        for mixer_out in sorted(self.device.config["mixer_out"]):
            self.notebook.append_page(MonoMixerPanel(self.device, mixer_out),
                                      Gtk.Label(mixer_out))
        self.notebook.append_page(router_vbox, Gtk.Label("Router"))
        self.notebook.connect("switch-page", self.on_notebook_switched_page)

        self.add(self.notebook)


    def on_src_combo_changed(self, combo, dest):
        self.device.route_mix(combo.get_active_text(), dest)

    def on_impedance_toggled(self, button, name):
        if button.get_active():
            button.set_label("INSTRUMENT")
            self.device.set_impedance(name, scarlett.IMPEDANCE_INST)
        else:
            button.set_label("LINE/MIC")
            self.device.set_impedance(name, scarlett.IMPEDANCE_LINE)

    def on_pad_toggled(self, button, name):
        if button.get_active():
            button.set_label("-10 dB")
            self.device.set_pad(name, scarlett.PAD_ON)
        else:
            button.set_label("OFF")
            self.device.set_pad(name, scarlett.PAD_OFF)

    def on_notebook_switched_page(self, notebook, page, page_num):
        if page_num == len(self.device.config["mixer_out"]):
            self.hb.props.subtitle = "Router & Switches"
        else:
            self.hb.props.subtitle = "MIX%d (%s)" % (page_num+1, "inactive")


# _____________________________________________________________________________


class MonoMixerMonoStrip(Gtk.Frame):

    def __init__(self, device, mixer_out, mixer_in, mixer_src="OFF"):
        Gtk.Frame.__init__(self)
        self.set_label(None)

        # set instance properties
        self.device = device
        self.mixer_src = mixer_src
        self.mixer_in = mixer_in
        self.mixer_out = mixer_out
        self.gain = 0

        self.combo_src = Gtk.ComboBoxText.new()
        for src in sorted(device.config["mixer_src"]):
            # id string and text string are the same:
            self.combo_src.append(id=src, text=src)
        self.combo_src.set_active_id("OFF")
        self.combo_src.set_wrap_width(4)
        self.combo_src.connect("changed", self.on_combo_src_changed)

        self.gain_fader = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL,
                                                   -128, 6, 10)
        self.gain_fader.set_digits(0)
        self.gain_fader.set_inverted(True)
        self.gain_fader.set_value_pos(Gtk.PositionType.BOTTOM)
        self.gain_fader.add_mark(0, Gtk.PositionType.LEFT, "0")
        self.gain_fader.add_mark(6, Gtk.PositionType.LEFT, "+6")
        # add mark: unicode:minus, unicode:infinity
        self.gain_fader.add_mark(-128, Gtk.PositionType.LEFT, u"\u2212\u221e")
        self.gain_fader.connect("change-value", self.on_gain_changed)

        self.level_bar = Gtk.LevelBar.new_for_interval(-128.0, 6.0)
        self.level_bar.set_orientation(Gtk.Orientation.VERTICAL)
        self.level_bar.set_inverted(True)

        self.hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        self.hbox.pack_start(self.gain_fader, False, False, 5)
        self.hbox.pack_start(self.level_bar, False, False, 5)

        self.vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.vbox.pack_start(self.combo_src, False, False, 0)
        self.vbox.pack_start(self.hbox, True, True, 0)

        self.add(self.vbox)

    def on_combo_src_changed(self, combo):
        mixer_src = combo.get_active_text()
        if mixer_src is not None:
            self.device.set_mixer_source(mixer_src, self.mixer_in)
            print "DEBUG: Connect mixer_src=%s with mixer_in=%s" \
                % (mixer_src, self.mixer_in)
            # GLib.free(mixer_src)
            # TODO: documentation says mixer_src must be freed. However, doing
            # so gives a ValueError...I am confused.

    def on_gain_changed(self, gtk_range, scroll_type, value):
        self.device.set_mixer_gain(self.mixer_in, self.mixer_out, value)
        print "DEBUG: Set mixer matrix element in=%s, out=%s to value=%g dB" \
            % (self.mixer_in, self.mixer_out, value)
        return False  # False = further process signal (e.g., fader animation)


    def get_mixer_src(self):
        return self.mixer_src

    def get_mixer_in(self):
        return self.mixer_in


# _____________________________________________________________________________


class MonoMixerPanel(Gtk.Bin):

    def __init__(self, device, mixer_out):
        Gtk.Bin.__init__(self)

        self.device = device
        self.mixer_out = mixer_out

        self.hbox = Gtk.HBox()

        mixer_strip_list = list()
        for strip in range(18):
            mixer_in = "CH_%02d" % (strip+1)
            ms = MonoMixerMonoStrip(self.device, mixer_out, mixer_in)
            mixer_strip_list.append(ms)
            self.hbox.pack_start(ms, False, False, 0)

        self.add(self.hbox)


# _____________________________________________________________________________


w = RedBeetWindow()
w.connect("delete-event", Gtk.main_quit)
w.show_all()
Gtk.main()
