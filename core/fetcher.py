"""数据获取"""
import requests


def get_anime_data(anime_id: int) -> dict:
    url = f"https://api.netaba.re/subject/{anime_id}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()
