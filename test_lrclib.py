import requests
url = "https://lrclib.net/api/search"
params = {"track_name": "Since Tum", "artist_name": "JANI"}
r = requests.get(url, params=params)
if r.status_code == 200:
    for item in r.json():
        print(item.get('trackName'), item.get('artistName'))
        if item.get('syncedLyrics'):
            print("SYNCED:", item.get('syncedLyrics')[:100])
        else:
            print("PLAIN:", item.get('plainLyrics')[:100])
