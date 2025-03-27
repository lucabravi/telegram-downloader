import os

import requests

tmdb_token = os.getenv('TMDB_TOKEN', '')

def find_title(title: str = ''):
    while True:
        url = f"https://api.themoviedb.org/3/search/tv?query={title}"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {tmdb_token}"
        }
        response = requests.get(url, headers=headers).json()['results']
        if len(response) == 0:
            if ' ' not in title:
                return None
            title = title.split()[0:-1]
            continue

        return response[0]['name']
    return title


print(find_title("Il mio matrimonio felice - WickedAnime"))
