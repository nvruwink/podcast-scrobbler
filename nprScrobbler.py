import requests, bs4, pylast, time, datetime, tabulate
from config import *

# Change to False to make this actually scrobble
TESTING = False
if TESTING:
    print("=========== TESTING! Will not scrobble ==========")

# Check artist
def check_artist(artist):
    artist_object = pylast.Artist(artist, network)
    corrected_artist_name = artist_object.get_correction()
    if (artist == corrected_artist_name):
        # No change, return immediately and don't waste server hits
        return artist
    corrected_artist_object = pylast.Artist(corrected_artist_name, network)
    if (artist_object != corrected_artist_object):
        response = input("Should artist "+artist+" be "+corrected_artist_name+"? (y/N)").lower()
        if (response == "y"):
            artist = corrected_artist_name
    elif (artist != corrected_artist_name):
        print("Suggested artist name correction does not affect scrobble, ignoring.")
    return artist

# Check track - takes strings, returns duple of string track name and Track object to avoid hitting the server multiple times
def check_track(track_name, artist):
    track = pylast.Track(artist, track_name, network)
    corrected_track_name = track.get_correction()
    if (track_name == corrected_track_name):
        # No change, return immediately and don't waste server hits
        return [track_name, track]
    corrected_track = pylast.Track(artist, corrected_track_name, network)
    if (corrected_track != track):
        response = input("Should song "+track_name+" be "+corrected_track_name+"? (y/N) ").lower()
        if (response == "y"):
            track_name = corrected_track_name
            track = corrected_track
    elif (track_name != corrected_track_name):
        print("Suggested song name correction does not affect scrobble, ignoring.")
    # Test track for errors
    try:
        track.get_listener_count()
    except pylast.WSError as e:
        response = input("Track not found! Would you like to (I)gnore this track, edit the (T)rack title, or edit the (A)rtist?").lower()
        if (response == "t"):
            response = input("Type a better track name: ")
            return check_track(response, artist)
        elif (response == "a"):
            response = input("Type a better artist name: ")
            return check_track(track_name, response)
        else:
            return ["",""]
    return [track_name,track]

# New Music Friday Parser
def get_tracks_friday(newMusic):
    print("Looks like a New Friday site.")
    # Based on visual inspection of 2 results, all featured songs are listed as li elements inside an ol element
    featuredList = newMusic.select('ol > li')

    # Save each song in a list of lists. Form will be [[song0, artist0, album0],[song1, artist1, album1],...]

    newSongs = []

    # Process list into songs, artists, and albums
    for e in featuredList:
        print("entry: "+e.getText())
        # Albums are inside <em> tags, grab them first using HTML parsing. Sometimes we may be missing an album title, e.g. for a single...
        # Also, it turns out sometimes the intern just forgets the <em> tag. :(
        # When this comes up, use a blank album string
        ems = e.select('em')
        if ems:
            album = ems[0].getText()
        else:
            album = ""

        # Artists and track names are only indicated with literal characters, need to be parsed out of the pure text.
        e = e.getText()
        # Strip the artist name from before the dash, leave the rest of the text in the buffer to be processed for track names
        # Apparently sometimes the intern uses a hyphen instead of a dash :(
        if " — " in e:
            (artist, e) = e.split(" — ",1)
        elif " - " in e:
            (artist, e) = e.split(" - ",1)
        else:
            print("Artist/track splitting dash not found, please check if the intern did something weird.")
            continue
        artist = check_artist(artist)
        if not artist:
            continue

        # Sometimes more than one song is featured from a single artist -
        # they should have double quotes surrounding them, but this may not be consistent.
        # 
        # Later we should parse the text and make sure the plurality of songs matches syntactically to "Songs:" or "Song:"

        songs = e.split('"')[1::2]
        for s in songs:
            (s, track) = check_track(s, artist)
            if not s:
                continue
            count = track.get_listener_count()
            newSongs.append([s, artist, album, count])

    return newSongs

# Guest DJ Parser
def get_tracks_guestdj(newMusic):
    print("Looks like a guest DJ/new mix NPR site.")
    # Based on visual inspection of 1 result, all featured songs are listed as h3 elements with class="edTag"
    featuredList = newMusic.select('h3[class="edTag"]')
    print(featuredList)

    # Save each song in a list of lists. Form will be [[song0, artist0, album0],[song1, artist1, album1],...]

    newSongs = []

    # Process list into songs, artists, and albums
    # Entries appear to be in the form:
    # 3. Artist: "Track Title" from <em>Album Title</em>
    #
    # Update 2021/12/05 - a late 2020 post had no numbers for the songs, need to parse:
    # Artist: "Track Title" from <em>Album Title</em>
    for e in featuredList:
        print("entry: "+e.getText())
        # Albums are inside <em> tags, grab them first using HTML parsing. Sometimes we may be missing an album title, e.g. for a single...
        # When this comes up, use a blank album string
        ems = e.select('em')
        if ems:
            album = ems[0].getText()
        else:
            album = ""

        # Artists and track names are only indicated with literal characters, need to be parsed out of the pure text.
        e = e.getText()
        # Remove the number, period, and space from the beginning of the string
        import re
        p = re.compile('\d+\. ')
        if p.match(e):
            (_, e) = e.split(". ",1)
        
        # Strip the artist name from before the colon, leave the rest of the text in the buffer to be processed for track names
        (artist, e) = e.split(": ",1)
        artist = check_artist(artist)
        if not artist:
            continue

        # Sometimes more than one song is featured from a single artist -
        # they should have double quotes surrounding them, but this may not be consistent.
        # 
        # Later we should parse the text and make sure the plurality of songs matches syntactically to "Songs:" or "Song:"

        songs = e.split('"')[1::2]
        for s in songs:
            (s, track) = check_track(s, artist)
            if not s:
                continue
            count = track.get_listener_count()
            newSongs.append([s, artist, album, count])

    return newSongs

# Set up Last.FM network

password_hash = pylast.md5(passwd)

network = pylast.LastFMNetwork(api_key=API_KEY, api_secret=API_SECRET,
                               username=username, password_hash=password_hash)

# Get website
site = input("Enter the New Music Friday URL: ")

# Download and process html
res = requests.get(site)
res.raise_for_status()
newMusic = bs4.BeautifulSoup(res.text, features="html.parser")

# Select correct parser, then get list of tracks
website_title = newMusic.select('title')[0].getText()
if ("New Music Friday" in website_title) or ("Best New Albums" in website_title):
    newSongs = get_tracks_friday(newMusic)
elif ("npr.org" in site):
    # Assume GuestDJ article
    newSongs = get_tracks_guestdj(newMusic)
else:
    print(newMusic.select('title')[0].getText()[:18]+" != New Music Friday: ")
    print("Not an NPR website, this functionality is not available yet.")
    exit() 

# Print table of newSongs
print(tabulate.tabulate(newSongs, headers=["Song","Artist","Album","Listener Count"]))

# Scrobble newSongs

response = input("Scrobble these? (Y/n)").lower()
if TESTING:
    print("TESTING flag set, scrobbles will not be sent.")
elif response == "n":
    exit()
else:
    print("Scrobbling...")
    for s in newSongs:
        network.scrobble(title=s[0], artist=s[1], album=s[2], timestamp=int(time.mktime(datetime.datetime.now().timetuple())))
    print("Succesful!")
