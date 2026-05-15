import logging
import requests
from services.lyrics import LyricsService

# Enable requests debug logging
import http.client as http_client
http_client.HTTPConnection.debuglevel = 1
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

s = LyricsService()
res = s.fetch("Since Tum", "JANI")
print(res)
