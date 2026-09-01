# -*- coding: utf-8 -*-
"""国籍 -> 电竞赛区映射。

原本住在 playerdb/build_db.py 里,但 `scraper/` 不进生产镜像(Dockerfile
只 COPY server/scripts/static/data),而管理页新增选手时要在服务端把国籍
推成赛区,所以挪到 server/ 下由两边共用——build_db 顶部已经把仓库根
插进 sys.path,直接 import 即可,不必留第二份表。
"""

# esports-style regions used for the "same region" (yellow) hint
REGION = {
    # Europe
    "Denmark": "Europe", "Sweden": "Europe", "Norway": "Europe", "Finland": "Europe",
    "France": "Europe", "Germany": "Europe", "Poland": "Europe", "Czech Republic": "Europe",
    "Czechia": "Europe", "Slovakia": "Europe", "United Kingdom": "Europe", "Spain": "Europe",
    "Portugal": "Europe", "Netherlands": "Europe", "Belgium": "Europe", "Bosnia and Herzegovina": "Europe",
    "Serbia": "Europe", "Croatia": "Europe", "Slovenia": "Europe", "Montenegro": "Europe",
    "North Macedonia": "Europe", "Macedonia": "Europe", "Bulgaria": "Europe", "Romania": "Europe",
    "Hungary": "Europe", "Austria": "Europe", "Switzerland": "Europe", "Italy": "Europe",
    "Greece": "Europe", "Turkey": "Europe", "Türkiye": "Europe", "Estonia": "Europe",
    "Latvia": "Europe", "Lithuania": "Europe", "Iceland": "Europe", "Ireland": "Europe",
    "Luxembourg": "Europe", "Malta": "Europe", "Kosovo": "Europe", "Albania": "Europe",
    "Moldova": "Europe",
    # CIS
    "Russia": "CIS", "Ukraine": "CIS", "Belarus": "CIS", "Kazakhstan": "CIS",
    "Uzbekistan": "CIS", "Kyrgyzstan": "CIS", "Armenia": "CIS", "Georgia": "CIS",
    "Azerbaijan": "CIS", "Tajikistan": "CIS",
    # Americas
    "United States": "North America", "Canada": "North America", "Mexico": "North America",
    "Brazil": "South America", "Argentina": "South America", "Chile": "South America",
    "Uruguay": "South America", "Peru": "South America", "Colombia": "South America",
    "Venezuela": "South America", "Ecuador": "South America", "Paraguay": "South America",
    "Bolivia": "South America", "Guatemala": "North America", "Costa Rica": "North America",
    "Dominican Republic": "North America",
    # Asia
    "China": "Asia", "Mongolia": "Asia", "South Korea": "Asia", "Japan": "Asia",
    "Taiwan": "Asia", "Hong Kong": "Asia", "Singapore": "Asia", "Malaysia": "Asia",
    "Indonesia": "Asia", "Thailand": "Asia", "Vietnam": "Asia", "Philippines": "Asia",
    "India": "Asia", "Pakistan": "Asia", "Bangladesh": "Asia", "Sri Lanka": "Asia",
    "Nepal": "Asia", "Myanmar": "Asia", "Laos": "Asia", "Cambodia": "Asia", "Macau": "Asia",
    # Oceania
    "Australia": "Oceania", "New Zealand": "Oceania",
    # Middle East & Africa
    "Israel": "Middle East & Africa", "Jordan": "Middle East & Africa",
    "Lebanon": "Middle East & Africa", "Saudi Arabia": "Middle East & Africa",
    "United Arab Emirates": "Middle East & Africa", "Qatar": "Middle East & Africa",
    "Kuwait": "Middle East & Africa", "Iraq": "Middle East & Africa",
    "Iran": "Middle East & Africa", "Egypt": "Middle East & Africa",
    "South Africa": "Middle East & Africa", "Morocco": "Middle East & Africa",
    "Tunisia": "Middle East & Africa", "Algeria": "Middle East & Africa",
    "Nigeria": "Middle East & Africa", "Kenya": "Middle East & Africa",
}


def region_of(country: str) -> str:
    return REGION.get(country, "Other")


_BY_FOLD = {c.casefold().replace(" ", ""): c for c in REGION}


def canonical_country(value: str) -> str | None:
    """把人工输入的国籍对回表里的标准写法,对不上返回 None。

    大小写/空格不符会同时打掉三样东西且都不报错:赛区退成 Other、国旗查不到、
    前端 COUNTRY_CN 查不到于是显示英文原文(线上真出现过 "russia")。
    """
    return _BY_FOLD.get((value or "").casefold().replace(" ", ""))
