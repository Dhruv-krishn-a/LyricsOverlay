from services.lyrics import LyricsService
s = LyricsService()
res = s.fetch("Since Tum", "JANI")
if res:
    print(f"Source: {res.source}")
    if res.synced:
        print("SYNCED LYRICS FOUND:")
        for line in res.synced.splitlines()[:5]:
            print(line)
    elif res.plain:
        print("ONLY PLAIN LYRICS FOUND:")
        for line in res.plain.splitlines()[:5]:
            print(line)
else:
    print("No lyrics found")
