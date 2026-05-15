import gi
import threading
import time
gi.require_version('Playerctl', '2.0')
from gi.repository import Playerctl, GLib

class TestService:
    def __init__(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        while not hasattr(self, 'manager'):
            time.sleep(0.01)
            
    def _run_loop(self):
        context = GLib.MainContext.new()
        context.push_thread_default()
        self.manager = Playerctl.PlayerManager()
        self.manager.connect("name-appeared", lambda m, n: print("Name appeared:", n.name))
        print("Initial players:", [n.name for n in self.manager.props.player_names])
        loop = GLib.MainLoop.new(context, False)
        loop.run()

s = TestService()
time.sleep(2)
print("Done")
