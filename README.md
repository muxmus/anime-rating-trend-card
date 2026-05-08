### anime-rating-trend-card

---

基于[netaba.re](https://netaba.re)，采用其api构建

可通过`bangumi_id`返回对应动画的评分趋势卡片

---

如《异国日记》493016 [https://bgm.tv/subject/493016](https://bgm.tv/subject/493016)

[https://img.muxmus.com/ani-card/493016](https://img.muxmus.com/ani-card/493016)

![](https://img.muxmus.com/ani-card/493016)

或jpg格式

[https://img.muxmus.com/ani-card/493016?type=jpg](https://img.muxmus.com/ani-card/493016?type=jpg)

![](https://img.muxmus.com/ani-card/493016?type=jpg)

---
确保依赖和字体：
```
pip install requests svgwrite
sudo apt install fonts-noto-cjk fonts-wqy-microhei
```
svg转jpg需要额外安装的库：
```
sudo apt install libcairo2
pip install cairosvg Pillow
```

局限性（待改进）：
- 主要展示放送期间的趋势，是高开低走还是稳居高位亦或有几个神回突然升高
- （已解决，老番从有数据(2018.05.16)开始展示，多集同时开播会合并省略）~~仅适用于新番，老番、OVA及剧场版会因为数据不全、多集同时开播等原因造成各种排版问题，后续可能优化~~
- （已解决）~~已知如《葬送的芙莉莲》400602等由于api中包含sp、oped等造成解析错误返回500，后续会根据`subject.eps[num].type`过滤~~

> *代码及以下说明由deepseek生成*
>
>  项目文件结构
>  
>  ```
>  ani-card-cc/
>  ├── main.py                  # 主入口：启动 HTTP 服务器
>  ├── README.md                # 本文件：文件结构说明
>  ├── core/
>  │   ├── __init__.py
>  │   ├── fetcher.py           # 数据获取：调用 API 获取动漫原始数据
>  │   ├── parser.py            # 数据解析：解析 JSON、过滤评分与剧集、时区转换
>  │   ├── smoothing.py         # 曲线平滑：Catmull-Rom/折线/移动平均/降采样
>  │   ├── svg_gen.py           # SVG 生成：坐标轴、网格、曲线、标签等渲染
>  │   ├── converter.py         # 格式转换：SVG → JPG（cairosvg + Pillow）
>  │   └── card.py              # 卡片编排：串联获取→解析→渲染的完整流程
>  └── server/
>      ├── __init__.py
>      └── handler.py           # HTTP 处理：路由解析、异常映射、响应输出
>  ```
>  
>   模块职责
>  
>  | 模块 | 职责 |
>  |------|------|
>  | `main.py` | 程序入口，创建 `HTTPServer` 并绑定 `AnimeCardHandler` |
>  | `core/fetcher.py` | 通过 `requests` 调用 `api.netaba.re` 获取动漫 JSON |
>  | `core/parser.py` | 解析原始 JSON，转换为北京时区，过滤未开播/开播后评分，提取剧集列表 |
>  | `core/smoothing.py` | 提供 Catmull-Rom→Bezier、折线生成、移动平均平滑、阶梯降采样 |
>  | `core/svg_gen.py` | 用 `svgwrite` 生成 1200×630 的评分趋势 SVG 卡片 |
>  | `core/converter.py` | SVG 转 JPEG（可选，依赖 cairosvg + Pillow） |
>  | `core/card.py` | 编排层，组合获取→解析→判断是否显示剧集→渲染 |
>  | `server/handler.py` | HTTP GET 处理，路径 `/{anime_id}`，查询参数 `?type=jpg` |
>  
>   数据流
>  
>  ```
>  HTTP GET /{id}
>    → server/handler.py
>      → core/card.py
>        → core/fetcher.py   (API 请求)
>        → core/parser.py    (JSON → 结构化数据)
>        → core/svg_gen.py   (数据 → SVG)
>          → core/smoothing.py (曲线计算)
>        → core/converter.py (SVG → JPG, 可选)
>      → HTTP Response (SVG/JPEG)
>  ```
>  
