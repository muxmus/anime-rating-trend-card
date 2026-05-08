"""数据解析与过滤"""
from datetime import datetime, timezone, timedelta

BJT = timezone(timedelta(hours=8))


class NotYetAired(Exception):
    """动画尚未开播异常"""
    pass


def parse_and_filter(data: dict) -> dict:
    subject = data.get("subject", {})

    if not subject.get("air_date"):
        raise NotYetAired("作品尚未公布播出日期或无有效开播信息")

    name_cn = subject.get("name_cn") or subject.get("name") or "未知作品"
    air_date_utc = datetime.fromisoformat(subject["air_date"].replace("Z", "+00:00"))
    air_date_bjt = air_date_utc.astimezone(BJT)

    # 获取所有 history 中最晚的 recordedAt
    history = data.get("history", [])
    max_recorded_bjt = None
    for item in history:
        if "recordedAt" not in item:
            continue
        dt_utc = datetime.fromisoformat(item["recordedAt"].replace("Z", "+00:00"))
        dt_bjt = dt_utc.astimezone(BJT)
        if max_recorded_bjt is None or dt_bjt > max_recorded_bjt:
            max_recorded_bjt = dt_bjt

    if max_recorded_bjt is None or air_date_bjt > max_recorded_bjt:
        raise NotYetAired("动画尚未开播，无有效评分记录")

    # 构建评分序列（仅保留开播之后的记录）
    scores = []
    for item in history:
        if "score" not in item:
            continue
        dt_utc = datetime.fromisoformat(item["recordedAt"].replace("Z", "+00:00"))
        dt_bjt = dt_utc.astimezone(BJT)
        if dt_bjt.date() >= air_date_bjt.date():
            scores.append({"date": dt_bjt, "score": item["score"]})

    # 剧集信息
    eps = []
    for item in subject.get("eps", []):
        if item.get("type") != 0:
            continue
        if not item.get("airdate"):
            continue
        dt_utc = datetime.fromisoformat(item["airdate"].replace("Z", "+00:00"))
        dt_bjt = dt_utc.astimezone(BJT)
        ep_name_cn = item.get("name_cn", "")
        ep_name = item.get("name", "")
        ep_display_name = ep_name_cn or ep_name
        eps.append({
            "sort": item["sort"],
            "name": ep_name,
            "name_cn": ep_display_name,
            "airdate": dt_bjt
        })

    total_users = subject.get("rating", {}).get("total")
    if total_users is None:
        total_users = 0

    return {
        "name_cn": name_cn,
        "air_date": air_date_bjt,
        "scores": scores,
        "eps": eps,
        "total_users": total_users
    }
