import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango, GLib

def on_activate(app):
    win = Gtk.ApplicationWindow(application=app)
    lbl = Gtk.Label()
    try:
        lbl.set_markup("<span color='#ffffff'>I've been</span>")
        print("Markup 1 successful")
        lbl.set_markup("<span color='#ffffff'>\"kiyon? kahan?\"</span>")
        print("Markup 2 successful")
        lbl.set_markup("<span color='#ffffff'>A & B</span>")
        print("Markup 3 successful")
    except Exception as e:
        print("Error:", e)
    
    app.quit()

app = Gtk.Application(application_id="dev.lyricfetch.testmarkup")
app.connect("activate", on_activate)
app.run()
