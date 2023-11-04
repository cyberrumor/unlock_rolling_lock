#!/usr/bin/env python3

import requests
import urllib
import sys
import os
import multiprocessing
from dataclasses import dataclass
from bs4 import BeautifulSoup
import base64
from time import sleep

URL = "https://www.wcostream.tv/"


@dataclass(order=True)
class Episode:
    title: str
    link: str
    selected: bool = False

    def __post_init__(self):
        self.link = URL + self.link

    def __str__(self):
        return self.title


class App:
    def __init__(self, show):
        if not show:
            print("Expected a show name.")
            exit()

        self.show = show
        self.session = requests.Session()
        self.episodes = []
        self.selections = []
        self.rate = 5

        # set up our headers so we don't look like a script.
        self.session.headers.update(
            {
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win 64; x64; rv:69.0) Gecko/20100101 Firefox/69.0",
                "Referer": URL,
            }
        )

        # This will be set to the show name
        self.search_title_key = "catara"

        # This will be set to either "series" or "episodes"
        self.search_type_key = "konuara"

        # This will be the class used to identify links
        self.episode_link_class = "sonra"

    def search(self):
        """
        Populates self.episodes with Episode objects.
        """
        search_response = self.session.post(
            URL + "/search",
            data={
                self.search_title_key: self.show,
                self.search_type_key: "episodes",
            },
        )
        assert (
            search_response.status_code == 200
        ), f"Received {search_response.status_code}, unable to search."

        if not (text := search_response.text):
            print("response had no text")
            exit()

        soup = BeautifulSoup(text, features="html.parser")

        for a in soup.find_all("a", attrs={"class": self.episode_link_class}):
            episode = Episode(a.get("title"), a.get("href"))
            if self.show not in episode.title.lower():
                # non-relevant hit
                continue

            if episode not in self.episodes:
                self.episodes.append(episode)

        self.episodes.sort()

    def decode(self, encoded_link):
        """
        Accepts a particular type of javascript snippet. This script is
        expected to contain an array of salted and encoded strings, with a
        large integer (the 'salt'), at some point after the end of the array.

        Once it decodes the array, it is loaded by BeautifulSoup. From here, it
        attempts to get the iframe and src elements. On failure at any point,
        it should return False (or error out and die).
        """
        start_index = encoded_link.find("[")
        start_index -= 1
        end_index = encoded_link.find("]")

        # get the salt, it is completely numeric
        salt = None
        for chunk in encoded_link[end_index::].split():
            if (salt := "".join([i for i in chunk if i.isalnum()])).isnumeric():
                salt = int(salt)
                break

        if not salt:
            return False

        # get the decoded html

        def decode(encoded_char):
            # absolute value of the base64 of the ascii encoded string
            # minus salt as a char.
            return chr(
                abs(
                    int(
                        "".join(
                            [
                                i
                                for i in base64.b64decode(
                                    encoded_char.encode("ascii")
                                ).decode("ascii")
                                if i.isnumeric()
                            ]
                        )
                    )
                    - salt
                )
            )
        with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
            decoded_html = "".join(
                pool.map(decode, encoded_link[start_index:end_index].split(", "))
            )

        soup = BeautifulSoup(decoded_html, features="html.parser")
        if not (iframe := soup.find("iframe")):
            return False

        if not (src := iframe.get("src")):
            return False

        return src

    def get_episode_download_links(self, episode):
        """
        Given an Episode object, this hits the episode.url (request 1) and
        locates a link (request 2) that will have the link (request 3) to the
        json that contains the video download location. This returns the video
        download location (there are two of these) along with the suspected
        file type.
        """
        self.dodge_rate_limit()
        episode_page_response = self.session.get(episode.link)
        episode_page_response.raise_for_status()

        if not (text := episode_page_response.text):
            raise ValueError(
                f"{episode_page_response.url=} responded with a blank .text property!"
            )

        # Look for a link to the page that will have the getvidlink.
        soup = BeautifulSoup(text, features="html.parser")
        if not (iframe := soup.find("iframe")):
            # There were no iframes. Look for the longest script.
            encoded_html = max((str(i) for i in soup.find_all("script")), key=len)
            # decode it.
            if not (video_page_link := self.decode(encoded_html)):
                # couldn't get either salt, iframe, or src.
                return None, None, None
        else:
            video_page_link = iframe.get("src")

        self.dodge_rate_limit()
        video_page = self.session.get(urllib.parse.unquote(video_page_link))
        soup = BeautifulSoup(video_page.text, features="html.parser")
        script_with_video_info_link = max(
            [i.text for i in soup.find_all("script")], key=len
        )

        # Find the video url from the script.
        start = script_with_video_info_link.find("/inc/embed/getvidlink.php?")
        end = script_with_video_info_link[start:].find('",') + start
        getvidlink_suffix = script_with_video_info_link[start:end]
        self.dodge_rate_limit()
        getvidlink = self.session.get(URL + getvidlink_suffix).json()

        download_url = getvidlink["cdn"] + "/getvid?evid=" + getvidlink["enc"]
        alt_url = getvidlink["server"] + "/getvid?evid=" + getvidlink["enc"]

        # default to mp4 if a file extension can't be identified.
        file_extension = ".mp4"
        for extension in [".mp4", ".mkv", ".avi"]:
            if extension in getvidlink_suffix.lower():
                file_extension = extension
                break

        return download_url, alt_url, file_extension

    def make_selections(self):
        """
        Allows the user to manipulate the "selected" property of episodes.
        On user input of "commit", returns.
        """
        while True:
            if sys.platform in ["linux", "linux2", "darwin"]:
                os.system("clear")
            print("ind | want | title")
            print("----|------|------")
            for index, item in enumerate(self.episodes):
                print(f"[{index}] [{item.selected}] {item}")

            try:
                choice = input(">_: ").lower()
                if choice == "commit":
                    return

                if choice in ["exit", "q", "quit"]:
                    exit()

                if choice == "select none":
                    for episode in self.episodes:
                        episode.selected = False
                    continue

                if choice == "select all":
                    for episode in self.episodes:
                        episode.selected = True
                    continue

                choice = int(choice)
                self.episodes[choice].selected = not self.episodes[choice].selected

            except ValueError:
                print("Enter a number to toggle selection or type 'commit'")
                print("You can try 'select all' or 'select none' as well.")
                input("[Enter]")

            except IndexError:
                print(f"Expected a value between {0} and {len(self.episodes) - 1}")
                input("[Enter]")

            except KeyboardInterrupt:
                print()
                exit()

    def dodge_rate_limit(self):
        """
        Simple handler to print a message and sleep.
        """
        print(f"waiting for rate limit: {self.rate}")
        sleep(self.rate)

    def run(self):
        """
        Main loop for the app.
        - Search self.show and populate self.episodes with Episode objects.
        - Prompt the user to select episodes for download.
        - Download the selected episodes.
        """
        self.search()
        if not self.episodes:
            print("No hits.")
            exit()

        self.make_selections()
        for episode in self.episodes:
            if not episode.selected:
                continue

            # Try to get a sane title.
            title = "".join(
                [i for i in episode.title if i.isalnum() or i in [" ", "_"]]
            ).replace(" ", "_")

            print(f"Locating {episode.title}")
            (
                download_link,
                alt_link,
                file_extension,
            ) = self.get_episode_download_links(episode)
            if not (download_link and alt_link and file_extension):
                print(f"Couldn't locate {episode.title}, skipping.")
                continue

            print(f"Saving as: {title}{file_extension}")
            try:
                r = self.session.get(download_link, stream=True)
                with open(f"{title}{file_extension}", "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)

            except:
                # try the other link
                r = self.session.get(alt_link, stream=True)
                with open(f"{title}{file_extension}", "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)


if __name__ == "__main__":
    show = " ".join(sys.argv[1:])
    app = App(show)
    app.run()
