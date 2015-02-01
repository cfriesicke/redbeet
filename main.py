#!/usr/bin/env python

from gi.repository import Gtk, GLib
import scarlett

#_______________________________________________________________________________

class RedBeetWindow(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self, title="RedBeet")
        self.set_border_width(10)
        self.set_default_size(400,600)

        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.props.title = "RedBeet"
        hb.props.subtitle = "Mixer"
        self.set_titlebar(hb)

        self.device = scarlett.Device()

        button_mixer = Gtk.Button.new_with_label("Mixer")
        button_mixer.connect("clicked", self.on_button_mixer_clicked)
        button_router = Gtk.Button.new_with_label("Router")
        button_router.connect("clicked", self.on_button_router_clicked)

        hbox_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_buttons.pack_start(button_mixer, False, False, 0)
        hbox_buttons.pack_start(button_router, False, False, 0)

        self.notebook = Gtk.Notebook()
        for mixer_out in sorted(self.device.config["mixer_out"].values()):
            self.notebook.append_page(MonoMixerPanel(self.device, mixer_out), Gtk.Label(mixer_out))
        self.notebook.connect("switch-page", self.on_notebook_switch_page)

        vbox_root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox_root.pack_start(hbox_buttons, False, False, 0)
        vbox_root.pack_start(self.notebook, True, True, 0)

        self.add(vbox_root)

    def on_button_mixer_clicked(self, widget):
        print "Mixer button clicked"

    def on_button_router_clicked(self, widget):
        print "Router button clicked"

    def on_notebook_switch_page(self, parent_notebook, page, page_num):
        print "switch-page triggered"

#_______________________________________________________________________________


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
        for src in device.config["mixer_src"]:
            self.combo_src.append(id=src, text=src) # id string and text string are the same
        self.combo_src.set_active_id("OFF")
        self.combo_src.set_wrap_width(4)
        self.combo_src.connect("changed", self.on_combo_src_changed)

        self.gain_fader = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, -128, 6, 10)
        self.gain_fader.set_digits(0)
        self.gain_fader.set_inverted(True)
        self.gain_fader.set_value_pos(Gtk.PositionType.BOTTOM)
        self.gain_fader.add_mark(0, Gtk.PositionType.LEFT, "0")
        self.gain_fader.add_mark(6, Gtk.PositionType.LEFT, "+6")
        self.gain_fader.add_mark(-128, Gtk.PositionType.LEFT, u"\u2212\u221e") # unicode:minus, unicode:infinity
        self.gain_fader.connect("change-value", self.on_gain_changed)

        self.level_bar = Gtk.LevelBar.new_for_interval(-128,6)
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
        if mixer_src != None:
            self.device.set_mixer_source(mixer_src, self.mixer_in)
            print "DEBUG: Connect mixer_src=%s with mixer_in=%s" % (mixer_src, self.mixer_in)
            #GLib.free(mixer_src)
            # TODO: documentation says mixer_src must be freed. However, doing
            # so gives a ValueError...I am confused.

    def on_gain_changed(self, gtk_range, scroll_type, value):
        print "Set mixer matrix element in=%s, out=%s to value=%g dB" % (self.mixer_in, self.mixer_out, value)

    def get_mixer_src():
        return self.mixer_src

    def get_mixer_in():
        return self.mixer_in

#_______________________________________________________________________________

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


#_______________________________________________________________________________

w = RedBeetWindow()
w.connect("delete-event", Gtk.main_quit)
w.show_all()
Gtk.main()
