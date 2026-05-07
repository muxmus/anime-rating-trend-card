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

> *代码由deepseek生成*
