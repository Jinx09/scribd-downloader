from bs4 import BeautifulSoup
import requests
import json
import re

from .. import internals
from .. import const


class Track:
    """
    A class for an audio chapter in a Scribd audiobook playlist.

    Parameters
    ----------
    track: `dict`
        A dictionary information about an audiobook chapter
        containing the keys: "url", "part_number" and "chapter_number".
    """

    def __init__(self, track):
        self.url = track["url"]
        self.part_number = track["part_number"]
        self.chapter_number = track["chapter_number"]
        self._track = track

    def download(self, path):
        """
        Downloads the audiobook chapter to the given path.
        """
        internals.download_stream(self.url, path)


class Playlist:
    """
    A class for a Scribd audiobook playlist.

    Parameters
    ----------
    title: `str`
        The title of the audiobook.

    playlist: `dict`
        A dictionary information about an audiobook playlist and
        its tracks containing the keys: "playlist", "expires" and
        "playlist_token".
    """

    def __init__(self, title, playlist):
        self.title = title
        self.tracks = [ Track(track) for track in playlist["playlist"] ]
        self._playlist = playlist
        self.download_paths = []

    def download(self):
        """
        Downloads all the chapters available in the playlist.
        """
        title = self.title
        for track in self.tracks:
            path = "{0}_{1}.mp3".format(title, track.chapter_number)
            dl_str = 'Downloading chapter-{0} ({1}) to "{2}"'.format(track.chapter_number,
                                                                   track.url,
                                                                   path)
            print(dl_str)
            track.download(path)
            self.download_paths.append(path)


class ScribdAudioBook:
    """
    A base class for downloading audiobooks off Scribd.

    Parameters
    ----------
    url: `str`
        A string containing Scribd audiobook URL.
    """

    def __init__(self, audiobook_url):
        scribd_id_search = re.search("[0-9]{9}", audiobook_url)
        scribd_id = scribd_id_search.group()

        self._audiobook_keys= None
        self._preview_url = None
        self._book_id = None
        self._author_id = None
        self._license_url = None
        self._license_id = None
        self._playlist_url = None
        self._authenticate_url = None
        self._title = None
        self._playlist = None

        self.audiobook_url = audiobook_url
        self.scribd_id = scribd_id
        self.session_key_header = {"Session-Key": "acea0b1d-62b9-4fb7-960b-06d9fbb4999d"}

        # Replace these cookie values with ones generated when logged into a
        # Scribd premium-account. This will allow access to full audiobooks.
        self.cookies = const.premium_cookies

    @property
    def audiobook_keys(self):
        """
        Stores scraped information for an audiobook.
        """
        if not self._audiobook_keys:
            self._audiobook_keys = self._scrape_audiobook()
        return self._audiobook_keys

    @property
    def preview_url(self):
        """
        The free-to-access URL of the audiobook.
        """
        if not self._preview_url:
            audiobook = self.audiobook_keys
            self._preview_url = audiobook["preview_url"]
        return self._preview_url

    @property
    def book_id(self):
        """
        The Book-ID of the audiobook.
        """
        if not self._book_id:
            audiobook = self.audiobook_keys
            self._book_id = audiobook["book_id"]
        return self._book_id

    @property
    def author_id(self):
        """
        The Author-ID of Scribd used to authenticate with
        https://api.findawayworld.com/.
        """
        if not self._author_id:
            audiobook = self.audiobook_keys
            self._author_id = audiobook["author_id"]
        return self._author_id

    @property
    def license_url(self):
        """
        Returns the URL used to fetch the License-ID.
        """
        if not self._license_url:
            self._license_url = "https://api.findawayworld.com/v4/accounts/scribd-{0}/audiobooks/{1}".format(self.author_id, self.book_id)
        return self._license_url

    @property
    def license_id(self):
        """
        Returns the License-ID to be used by Scribd to fetch
        the audiobook content from http://api.findawayworld.com/.
        """
        if not self._license_id:
            requests.get(self.authenticate_url, cookies=self.cookies)
            response = requests.get(self.license_url, headers=self.session_key_header)
            response_dict = json.loads(response.text)
            self._license_id = response_dict["licenses"][0]["id"]
        return self._license_id

    @property
    def playlist_url(self):
        """
        Returns the audiobook playlist URL.
        """
        if not self._playlist_url:
            self._playlist_url = "https://api.findawayworld.com/v4/audiobooks/{}/playlists".format(self.book_id)
        return self._playlist_url

    @property
    def authenticate_url(self):
        """
        Authentication URL for premium Scribd accounts
        (if this didn't exist, we would have been able to download
        complete audiobooks off Scribd without needing a premium account).
        """
        if not self._authenticate_url:
            self._authenticate_url ="https://www.scribd.com/listen/{}".format(self.scribd_id)
        return self._authenticate_url

    @property
    def premium_cookies(self):
        """
        Returns a boolean based on whether the user is authenticated
        with a premium Scribd account.
        """
        return bool(self.author_id)

    @property
    def title(self):
        """
        Scrapes the title of the Scribd document.
        """
        if not self._title:
            splits = self.audiobook_url.split("/")
            splits.remove("")
            self._title = splits[-1].replace("-", " ")
        return self._title

    @property
    def playlist(self):
        """
        Returns a `Playlist` object.
        """
        if not self._playlist:
            self._playlist = Playlist(self.title.replace(" ", "_"), self.make_playlist())
        return self._playlist

    def _scrape_audiobook(self):
        """
        Scrapes the provided audiobook URL for information scraps.
        """
        response = requests.get(self.audiobook_url, cookies=self.cookies)
        soup = BeautifulSoup(response.text, "html.parser")

        div_tag = soup.find("div", {"data-track_category": "book_preview"})
        text = json.loads(div_tag["data-push_state"])
        preview_url = text["audiobook_sample_url"]
        book_id_search = re.search("[0-9]{5,6}", preview_url)
        book_id = book_id_search.group()

        js_tag = soup.find_all("script", {"type": "text/javascript"})[-1]
        js_code = js_tag.get_text()
        author_id_search = re.search("[0-9]{8}", js_code)
        author_id = author_id_search.group() if author_id_search else None

        return {"preview_url": preview_url, "book_id": book_id, "author_id": author_id}

    def make_playlist(self):
        """
        Generates a playlist dictionary based on whether the user
        is authenticated with a premium Scribd account or not.
        """
        if self.premium_cookies:
            data = '{"license_id":"' + self.license_id + '"}'
            response = requests.post(self.playlist_url, headers=self.session_key_header, data=data)
            playlist = json.loads(response.text)
        else:
            playlist = {"playlist": [{"url": self.preview_url,
                                     "part_number": "preview",
                                     "chapter_number": "preview"}],
                        "expires": None,
                        "playlist_token": None}

        return playlist
