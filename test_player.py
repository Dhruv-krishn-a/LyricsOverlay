from core.config import load_config
from services.player import PlayerService
import time
import gi
gi.require_version('Playerctl', '2.0')
from gi.repository import Playerctl

s = PlayerService()
time.sleep(0.5)
if s.manager.props.players:
    p = s.manager.props.players[0]
    print("Name type:", type(p.props.player_name))
    print("Name:", p.props.player_name)
    try:
        print("Name.name:", p.props.player_name.name)
    except Exception as e:
        print("Error:", e)
