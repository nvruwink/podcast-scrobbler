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
    if not corrected_artist_name:
        print('No suggested artist.')
        return artist
    if (artist == corrected_artist_name):
        # No change, return immediately and don't waste server hits
        return artist
    corrected_artist_object = pylast.Artist(corrected_artist_name, network)
    if (artist_object != corrected_artist_object):
        response = input(f"Should artist {artist} be {corrected_artist_name}? (y/N)").lower()
        if (response == "y"):
            artist = corrected_artist_name
    elif (artist != corrected_artist_name):
        print("Suggested artist name correction does not affect scrobble, ignoring.")
    return artist

# Check album - takes strings, returns string
def check_album(artist, album):
    album_object = network.get_album(artist, album)
    corrected_album_name = pylast._extract(album_object._request(album_object.ws_prefix + ".getCorrection"), "name")
    if not corrected_album_name:
        print('No suggested album.')
        return album
    if (album == corrected_album_name):
        # No change, return immediately and don't waste server hits
        return album
    elif album == "" and not corrected_album_name:
        # Blank album
        return album
    corrected_album_object = network.get_album(artist, corrected_album_name)
    if (album_object != corrected_album_object):
        response = input(f'Should album {album} be {corrected_album_name}? (y/N)').lower()
        if (response == "y"):
            album = corrected_album_name
    elif (album != corrected_album_name):
        print(f"Suggested album name correction {corrected_album_name} does not affect scrobble, recommend changing.")
        response = input(f'Should album {album} be {corrected_album_name}? (Y/n)').lower()
        if (response == "n"):
            pass
        else:
            album = corrected_album_name
    return album
    

# Check track - takes strings, returns duple of string track name and Track object to avoid hitting the server multiple times
def check_track(track_name, artist):
    if track_name.endswith(','):
        response = input(f"Should song {track_name} be {track_name[0:-1]}? (Y/n) ").lower()
        if (response != 'n'):
            track_name = track_name[0:-1]

    track = pylast.Track(artist, track_name, network)
    corrected_track_name = track.get_correction()
    if not corrected_track_name:
        print('No suggested track name.')
    elif (track_name == corrected_track_name):
        # No change, jump to test immediately and don't waste server hits
        #return [track_name, track]
        pass
    else:
        corrected_track = pylast.Track(artist, corrected_track_name, network)
        if not corrected_track:
            print(f'no server response for {artist} {corrected_track_name}, error')
            exit()
        if (corrected_track != track):
            response = input(f"Should song {track_name} be {corrected_track_name}? (y/N) ").lower()
            if (response == "y"):
                track_name = corrected_track_name
                track = corrected_track
        elif (track_name != corrected_track_name):
            print("Suggested song name correction does not affect scrobble, ignoring.")

    # Test track for errors
    try:
        track.get_listener_count()
    except pylast.WSError as e:
        response = input(f"Track {track_name} by Artist {artist} not found! Would you like to (I)gnore this track, edit the (T)rack title, or edit the (A)rtist?").lower()
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
        # Sometimes an "11th" featured album is featured with the text "Bonus Album: " at the beginning
        if 'Bonus Album: ' in e:
            (_, e) = e.split('Bonus Album: ',1)
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

        album = check_album(artist, album)

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
    if not featuredList:
        featuredList = newMusic.select('ol[class="edTag"]')
    if not featuredList:
        print('Error: No songs??!')
        exit()
    print(featuredList)

    # Save each song in a list of lists. Form will be [[song0, artist0, album0],[song1, artist1, album1],...]

    newSongs = []

    # Process list into songs, artists, and albums
    # Entries appear to be in the form:
    # 3. Artist: "Track Title" from <em>Album Title</em>
    #
    # Update 2021/12/05 - a late 2020 post had no numbers for the songs, need to parse:
    # Artist: "Track Title" from <em>Album Title</em>
    #
    # Sometimes there is no album listed, and sometimes this form uses a comma instead of colon to separate artist and track

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
        
        # Strip the artist name from before the colon or comma, leave the rest of the text in the buffer to be processed for track names
        if ':' in e:
            (artist, e) = e.split(": ",1)
        elif ',' in e:
            (artist, e) = e.split(", ",1)
        else:
            artist = e

        artist = check_artist(artist)
        if not artist:
            continue
        
        album = check_album(artist, album)

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
if ("New Music Friday" in website_title) or ("Best New Albums" in website_title) or ('new-music-friday' in site):
    newSongs = get_tracks_friday(newMusic)
elif ("npr.org" in site):
    # Assume GuestDJ article
    newSongs = get_tracks_guestdj(newMusic)
else:
    print(newMusic.select('title')[0].getText()[:18]+" != New Music Friday: ")
    print("Not an NPR website, this functionality is not available yet.")
    exit() 


# Scrobble newSongs
def scrobble_songs(newSongs):
    # Add Element # to list
    for (n, track) in enumerate(newSongs):
        if len(track) == 4:
            track.insert(0,n)
        elif len(track) == 5:
            track[0] = n
        else:
            print(f'Malformed track element {track}')

    # Print table of newSongs
    print(tabulate.tabulate(newSongs, headers=["#","Song","Artist","Album","Listener Count"]))

    response = input("Scrobble these? (Y/n)").lower()
    if response == "n":
        response = input('[E]dit or [q]uit?').lower()
        if response == "q":
            exit()
        else:
            try:
                response = int(input('Edit which # in table? (starts at 0)'))
            except:
                print("Not a number, try again")
                try:
                   response = int(input('Edit which # in table? (starts at 0)'))
                except:
                    print("Giving up")
                    exit()

            newSongs = edit_song(newSongs, response)
            scrobble_songs(newSongs)
            return
    else:
        if TESTING:
            print("TESTING flag set, scrobbles will not be sent.")
            exit()
        print("Scrobbling...")
        for s in newSongs:
            network.scrobble(title=s[0], artist=s[1], album=s[2], timestamp=int(time.mktime(datetime.datetime.now().timetuple())))
        print("Succesful!")
        exit()

def edit_song(newSongs, n):
    (_, song, artist, album, count) = newSongs[n]
    response = input(f'Edit which element?\n[a]rtist {artist}\nal[b]um {album}\n[s]ong {song}').lower()
    if response == 'a':
        artist = input('New artist name:')
    elif response == 'b':
        album = input('New album name:')
    elif response == 's':
        song = input('New song name:')

    response = input('[S]crobble or [e]dit this track further?').lower()
    if response == 'e':
        return edit_song(newSongs, n)
    else:
        (song, track) = check_track(song, artist)
        if not song:
            return
        count = track.get_listener_count()
        newSongs[n] = [song, artist, album, count]
        return newSongs

scrobble_songs(newSongs)
