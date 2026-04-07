import requests
from config import GOOGLE_MAPS_API_KEY
from sheets_client import add_lead


def search_orthodontists(city):

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"

    params = {
        "query": f"ortodoncista en {city}",
        "key": GOOGLE_MAPS_API_KEY
    }

    r = requests.get(url, params=params)

    data = r.json()

    for place in data["results"]:

        name = place["name"]

        print("Encontrado:", name)

        add_lead(name, "", "ortodoncista", "google_maps")


if __name__ == "__main__":

    search_orthodontists("La Plata")