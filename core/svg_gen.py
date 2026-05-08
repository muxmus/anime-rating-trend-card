"""SVG 卡片生成"""
import math
from datetime import timedelta
import svgwrite


def nice_step(rough: float) -> float:
    """返回一个美观的坐标轴步长"""
    if rough <= 0.1:
        return 0.1
    factor = 10 ** math.floor(math.log10(rough))
    normalized = rough / factor
    for candidate in [1, 2, 5, 10]:
        if candidate >= normalized:
            step = candidate * factor
            return max(0.1, step)
    return 10 * factor


def generate_svg(cooked: dict, show_eps_and_title: bool = True) -> str:
    WIDTH, HEIGHT = 1200, 630
    PAD_L, PAD_R, PAD_T, PAD_B = 100, 50, 50, 80
    COMPRESS_RATIO = 0.12

    plot_w = WIDTH - PAD_L - PAD_R
    normal_w = plot_w * (1 - COMPRESS_RATIO)
    compress_w = plot_w * COMPRESS_RATIO

    if not cooked["scores"]:
        raise ValueError("没有可用的评分数据")

    # 根据是否包含剧集信息选择不同的横轴计算方式
    if not show_eps_and_title:
        score_dates = [s["date"] for s in cooked["scores"]]
        first_date = min(score_dates)
        normal_end_date = max(score_dates)
        is_finished = False
        normal_w = plot_w
        compress_w = 0
        eps_sorted = []
    else:
        eps_sorted = sorted(cooked["eps"], key=lambda e: e["airdate"])
        if not eps_sorted:
            show_eps_and_title = False
            score_dates = [s["date"] for s in cooked["scores"]]
            first_date = min(score_dates)
            normal_end_date = max(score_dates)
            is_finished = False
            normal_w = plot_w
            compress_w = 0
            eps_sorted = []
        else:
            latest_record = cooked["scores"][-1]["date"]
            last_ep_airdate = eps_sorted[-1]["airdate"]
            is_finished = last_ep_airdate <= latest_record

            if is_finished:
                max_date = latest_record
                normal_end_date = last_ep_airdate
            else:
                next_ep = next((ep for ep in eps_sorted if ep["airdate"] > latest_record), None)
                if next_ep is None:
                    is_finished = True
                    max_date = latest_record
                    normal_end_date = last_ep_airdate
                else:
                    max_date = next_ep["airdate"]
                    normal_end_date = next_ep["airdate"]

            first_date = cooked["air_date"]
            normal_w = plot_w * (1 - COMPRESS_RATIO)
            compress_w = plot_w * COMPRESS_RATIO

    span_normal = max(1, (normal_end_date - first_date).days)

    if is_finished and show_eps_and_title:
        compress_start = last_ep_airdate
        compress_end = latest_record
        span_compress = max(1, (compress_end - compress_start).days)
    else:
        compress_start = normal_end_date
        compress_end = normal_end_date
        span_compress = 1

    def x_pos(d):
        if d <= normal_end_date:
            ratio = max(0, (d - first_date).days / span_normal)
            return PAD_L + ratio * normal_w
        elif is_finished and show_eps_and_title:
            days_past = max(0, (d - compress_start).days)
            ratio = math.sqrt(days_past / span_compress)
            return PAD_L + normal_w + ratio * compress_w
        else:
            return PAD_L + normal_w

    scores = [s["score"] for s in cooked["scores"]]
    min_s, max_s = min(scores), max(scores)
    score_range = max_s - min_s

    step = nice_step(score_range / 4.0) if score_range > 0 else 0.1
    y_min = max(0.0, step * (math.floor(min_s / step) - 1))
    y_max = step * (math.ceil(max_s / step) + 1)
    if y_max <= y_min + step:
        y_max = y_min + step

    plot_h = HEIGHT - PAD_T - PAD_B

    def y_pos(s):
        ratio = (s - y_min) / (y_max - y_min) if y_max > y_min else 0.5
        return HEIGHT - PAD_B - ratio * plot_h

    dwg = svgwrite.Drawing(size=(WIDTH, HEIGHT))
    dwg.embed_stylesheet("""
        .grid { stroke: #e8e8e8; stroke-width: 1; }
        .axis { stroke: #555; stroke-width: 2; }
        .curve { fill: none; stroke: #4A90D9; stroke-width: 4; }
        .title { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 30px; font-weight: bold; fill: #333; }
        .score-text { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 38px; font-weight: bold; fill: #4A90D9; }
        .user-text { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 18px; font-weight: 600; fill: #666; }
        .ep-label {
            font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 14px; font-weight: bold; fill: #555; opacity: 0.5;
            text-anchor: start;
        }
        .date-label { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 13px; font-weight: bold; fill: #999; }
        .y-label { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 14px; font-weight: bold; fill: #999; }
    """)
    dwg.add(dwg.rect(insert=(0, 0), size=(WIDTH, HEIGHT), fill="#fafafa"))

    # 网格线与Y轴标签
    y_val = y_min
    while y_val <= y_max + 1e-9:
        y = y_pos(y_val)
        dwg.add(dwg.line((PAD_L, y), (WIDTH - PAD_R, y), class_="grid"))
        dwg.add(dwg.text(f"{y_val:.1f}", insert=(PAD_L - 10, y + 5), class_="y-label", text_anchor="end"))
        y_val += step

    dwg.add(dwg.line((PAD_L, HEIGHT - PAD_B), (WIDTH - PAD_R, HEIGHT - PAD_B), class_="axis"))

    # 剧集信息（仅当显示时）
    if show_eps_and_title:
        merged_eps = []
        i = 0
        while i < len(eps_sorted):
            ep = eps_sorted[i]
            airdate = ep["airdate"]
            same_day = [ep]
            j = i + 1
            while j < len(eps_sorted) and eps_sorted[j]["airdate"].date() == airdate.date():
                same_day.append(eps_sorted[j])
                j += 1
            first_ep = same_day[0]
            last_ep = same_day[-1]
            sort_min = first_ep["sort"]
            sort_max = last_ep["sort"]
            name_cn = first_ep["name_cn"]
            if len(same_day) == 1:
                label = f"EP{sort_min} {name_cn}" if name_cn else f"EP{sort_min}"
            else:
                label = f"EP{sort_min}-{sort_max} {name_cn} 等" if name_cn else f"EP{sort_min}-{sort_max}"
            merged_eps.append({"airdate": airdate, "label": label})
            i = j

        ep_dates = {ep["airdate"].date() for ep in merged_eps}
    else:
        merged_eps = []
        ep_dates = set()

    # 横轴刻度与日期
    if show_eps_and_title:
        day = first_date
        while day <= normal_end_date:
            x = x_pos(day)
            dwg.add(dwg.line((x, HEIGHT - PAD_B - 4), (x, HEIGHT - PAD_B + 4), class_="axis"))
            if day.date() == first_date.date() or day.date() == normal_end_date.date() or day.date() in ep_dates:
                if day.date() == first_date.date():
                    date_str = f"{day.year % 100}.{day.month}.{day.day}"
                else:
                    date_str = f"{day.month}.{day.day}"
                dwg.add(dwg.text(date_str, insert=(x, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))
            day += timedelta(days=7)

        if is_finished:
            x_end = x_pos(latest_record)
            dwg.add(dwg.line((x_end, HEIGHT - PAD_B - 4), (x_end, HEIGHT - PAD_B + 4), class_="axis"))
            dwg.add(dwg.text("now", insert=(x_end, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))
    else:
        x_start = x_pos(first_date)
        dwg.add(dwg.line((x_start, HEIGHT - PAD_B - 4), (x_start, HEIGHT - PAD_B + 4), class_="axis"))
        start_date_str = f"{first_date.year % 100}.{first_date.month}.{first_date.day}"
        dwg.add(dwg.text(start_date_str, insert=(x_start, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))

        x_end = x_pos(normal_end_date)
        dwg.add(dwg.line((x_end, HEIGHT - PAD_B - 4), (x_end, HEIGHT - PAD_B + 4), class_="axis"))
        dwg.add(dwg.text("now", insert=(x_end, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))

    # 剧集小标题（仅当显示时）
    if show_eps_and_title:
        for ep in merged_eps:
            if ep["airdate"] < first_date or ep["airdate"] > max_date:
                continue
            x = x_pos(ep["airdate"])
            anchor_x = x + 16
            anchor_y = HEIGHT - PAD_B - 12
            dwg.add(dwg.text(
                ep["label"],
                insert=(anchor_x, anchor_y),
                transform=f"rotate(-90, {anchor_x}, {anchor_y})",
                class_="ep-label"
            ))

    # ---------- 曲线生成 ----------
    from .smoothing import catmull_rom_to_bezier, generate_polyline, moving_average_smooth, downsample_points

    sorted_scores = sorted(cooked["scores"], key=lambda x: x["date"])
    deduped = []
    for s in sorted_scores:
        if not deduped or s["date"] != deduped[-1]["date"]:
            deduped.append(s)
        else:
            deduped[-1] = s

    raw_points = [(x_pos(s["date"]), y_pos(s["score"])) for s in deduped]

    base_dist = 10.0
    if len(raw_points) > 5000:
        min_pixel_dist = base_dist * 4
    elif len(raw_points) > 2000:
        min_pixel_dist = base_dist * 2
    elif len(raw_points) > 500:
        min_pixel_dist = base_dist * 1.5
    else:
        min_pixel_dist = base_dist

    sparse = downsample_points(raw_points, min_pixel_dist=min_pixel_dist)
    smoothed = moving_average_smooth(sparse, window=3)

    if len(smoothed) >= 3:
        path_d = catmull_rom_to_bezier(smoothed, tension=0.1)
    elif len(smoothed) == 2:
        path_d = generate_polyline(smoothed)
    else:
        path_d = ""

    if path_d:
        dwg.add(dwg.path(d=path_d, class_="curve"))

    # 动画总标题
    dwg.add(dwg.text(cooked["name_cn"], insert=(PAD_L, 44), class_="title"))

    # 最新评分与评价人数
    latest_score = round(cooked["scores"][-1]["score"], 1)
    total_users = cooked["total_users"]
    user_text = f"{total_users}人评价"
    digit_chars = len(str(total_users))
    user_est_width = digit_chars * 9 + 3 * 18
    score_x = WIDTH - PAD_R - user_est_width - 20
    dwg.add(dwg.text(f"{latest_score:.1f}",
                     insert=(score_x, 44),
                     class_="score-text",
                     text_anchor="end"))
    dwg.add(dwg.text(user_text,
                     insert=(WIDTH - PAD_R, 44),
                     class_="user-text",
                     text_anchor="end"))

    return dwg.tostring()
