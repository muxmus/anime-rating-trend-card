"""卡片生成（编排层）"""
from .fetcher import get_anime_data
from .parser import parse_and_filter
from .svg_gen import generate_svg


def generate_card(anime_id: int, fmt: str = "svg") -> tuple[bytes, str]:
    raw = get_anime_data(anime_id)
    cooked = parse_and_filter(raw)

    scores_sorted = sorted(cooked["scores"], key=lambda x: x["date"])
    eps_sorted = sorted(cooked["eps"], key=lambda e: e["airdate"])
    show_eps_and_title = True
    if eps_sorted and scores_sorted:
        last_ep_date = eps_sorted[-1]["airdate"]
        first_score_date = scores_sorted[0]["date"]
        if first_score_date > last_ep_date:
            show_eps_and_title = False

    svg_str = generate_svg(cooked, show_eps_and_title=show_eps_and_title)

    if fmt == "jpg":
        try:
            from .converter import svg_to_jpg
            jpg_bytes = svg_to_jpg(svg_str)
            return jpg_bytes, "image/jpeg"
        except Exception:
            pass
    return svg_str.encode("utf-8"), "image/svg+xml"
