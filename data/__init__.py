# -*- coding: utf-8 -*-
"""
数据层模块

提供行情数据获取、本地存储、格式转换等功能。

组件:
    DataProvider       — XTquant 行情数据封装层
    Database           — SQLite + Parquet 混合存储
    Downloader         — 数据批量下载器
    qlib_converter     — Parquet → qlib 二进制格式转换
    backtrader_feeder  — Parquet → backtrader 数据源适配
"""
from .xt_provider import DataProvider
from .database import Database
from .downloader import Downloader
