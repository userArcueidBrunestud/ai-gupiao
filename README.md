# ai-gupiao — A-Share Intelligent Analysis System

A 股智能分析系统，基于 Python 构建，支持数据采集、技术指标分析和 AI 智能预测。

## 快速开始

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 复制环境变量
cp .env.example .env

# 运行测试
pytest tests/ -v
```

## 项目结构

```
ai-gupiao/
├── config/          # 配置管理 (pydantic-settings)
├── src/
│   ├── core/        # 数据模型 + 异常定义
│   ├── data/        # 数据采集 (akshare) + 持久化 (SQLite)
│   ├── analysis/    # 技术指标 (MA/RSI/MACD/Bollinger)
│   ├── ai/          # AI 特征工程 + 预测模型
│   ├── pipeline/    # 全流程编排器
│   └── utils/       # 日志 + 工具函数
├── tests/           # 单元测试
├── data/            # 本地数据库 & 模型文件
├── notebooks/       # Jupyter 分析笔记本
└── scripts/         # 一次性脚本 & CLI 入口
```

## 功能

- **数据采集** — 基于 akshare 获取 A 股历史日K线、实时行情
- **技术指标** — 移动平均线、RSI、MACD、布林带，支持注册表扩展
- **AI 预测** — sklearn 模型（默认随机森林），趋势方向预测
- **本地存储** — SQLite 本地化存储，无需外部数据库
