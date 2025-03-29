# Ybb-YieldBettingBias

一个基于 Python 的自动化投注分析工具。

## 功能特点

- 自动数据采集
- OCR 文字识别
- 赔率分析
- Kelly 公式计算

## 环境要求

- Python 3.x
- 相关依赖包（见 requirements.txt）

## 安装说明

1. 克隆仓库
```bash
git clone https://github.com/1imbic/Ybb-YieldBettingBias.git
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

## 使用方法

1. 配置 config.yaml
2. 运行主程序
```bash
python main.py
```

## 项目结构

- `main.py`: 主程序入口
- `init_manager.py`: 初始化管理
- `screen_manager.py`: 屏幕管理
- `data_manager.py`: 数据管理
- `fetch_odds.py`: 赔率获取
- `team_match.py`: 队伍匹配
- `kelly_calculator.py`: Kelly公式计算
- `config/`: 配置文件目录
- `ppocr_v4/`: OCR模型文件

## 许可证

MIT License 