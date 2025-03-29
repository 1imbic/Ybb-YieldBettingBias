# 小黑盒赔率收集系统流程分析

## 项目概述

本项目是一个自动化数据收集系统，用于从小黑盒应用中获取电子竞技比赛的赔率数据。系统通过模拟器运行小黑盒应用，使用OCR技术识别界面内容，并与网络数据源进行匹配和整合。

## 模块依赖关系

```
main.py
  ├── init_manager.py
  ├── screen_manager.py
  ├── data_manager.py
  ├── fetch_odds.py
  └── team_match.py
```

## 运行流程详解

### 1. 初始化阶段 (InitManager)

`init_manager.py` 负责系统的初始化工作，提供了以下功能：

- **加载配置文件**：从 `config.yaml` 读取系统配置
- **启动模拟器**：调用配置中指定的模拟器路径启动模拟器
- **连接ADB**：建立与模拟器的ADB连接，用于后续的界面控制
- **初始化OCR**：加载PaddleOCR模型，用于识别界面文本
- **启动小黑盒应用**：通过ADB命令启动小黑盒应用

调用顺序：`initialize_all()` → `start_emulator()` → `connect_adb()` → `launch_app()` → `initialize_ocr()`

输入：配置文件路径
输出：controller（ADB控制器）和 ocr（OCR识别器）对象

### 2. 屏幕管理 (ScreenManager)

`screen_manager.py` 负责与模拟器界面交互，包括：

- **屏幕识别**：截图并识别界面元素
- **界面操作**：点击、滑动等操作
- **数据提取**：从界面提取比赛信息
- **导航操作**：切换游戏项目、刷新界面等

核心功能是 `fetch_lbb_data()`，它获取小黑盒界面上的比赛信息。流程为：
1. 切换到指定游戏项目（如CS2、Dota2等）
2. 刷新界面并寻找"预测中"的比赛
3. 点击"预测中"按钮并截取信息
4. 处理获取的文本数据

输入：controller、ocr、游戏名称
输出：从界面提取的比赛数据列表

### 3. 数据处理 (DataManager)

`data_manager.py` 负责处理和存储数据：

- **文本处理**：解析从OCR获取的文本数据，提取比赛名称、队伍名称、赔率等信息
- **时间解析**：将识别到的时间格式化为标准格式
- **数据存储**：将处理后的数据保存到SQLite数据库

主要调用流程：
1. `process_text_data()`：处理OCR文本，提取结构化信息
2. `parse_extended_time()`：解析时间信息
3. `save_to_sqlite()`：将数据保存到数据库

输入：OCR提取的文本数据
输出：结构化的比赛数据，并存储到数据库

### 4. 网络数据获取 (fetch_odds)

`fetch_odds.py` 负责从网络获取比赛信息和赔率：

- **浏览器自动化**：使用Selenium控制浏览器访问网页
- **数据提取**：从网页解析比赛信息、队伍名称和赔率
- **数据存储**：将网络数据保存到SQLite数据库
- **缓存机制**：使用TTLCache缓存请求结果，减少重复请求

主要函数 `fetch_team_odds()` 完成从配置的URL获取比赛数据的工作。

输入：配置信息、URLs
输出：网络获取的比赛数据

### 5. 团队匹配 (team_match)

`team_match.py` 负责匹配来自不同来源的队伍和比赛名称：

- **初始化数据库**：创建或连接映射数据库
- **队伍匹配**：使用模糊匹配算法匹配不同来源的队伍名称
- **比赛匹配**：匹配不同来源的比赛名称
- **数据替换**：用标准化的队伍和比赛名称替换原始名称

主要函数：
- `match_teams_and_names()`：将网络数据与小黑盒数据中的队伍和比赛名称进行匹配
- `replace_team_and_match_name()`：用标准名称替换原始名称

输入：网络数据、小黑盒数据
输出：名称映射关系和替换后的数据

### 6. 主流程 (main.py)

`main.py` 协调整个系统的运行：

1. **加载配置**：读取 `config.yaml` 配置文件
2. **初始化系统**：调用 `InitManager` 初始化模拟器、ADB和OCR
3. **导航到比赛界面**：通过 `ScreenManager` 导航到赛事中心
4. **循环处理游戏项目**：对配置中的每个游戏项目执行以下步骤：
   - 获取网络数据（`fetch_team_odds`）
   - 获取小黑盒界面数据（`fetch_lbb_data`）
   - 匹配队伍和比赛名称（`match_teams_and_names`）
   - 替换标准化名称（`replace_team_and_match_name`）
   - 保存到数据库（`save_to_sqlite`）

## 数据流向

1. 配置文件 → `InitManager` → 系统初始化
2. 模拟器界面 → `ScreenManager` → OCR文本数据
3. OCR文本数据 → `DataManager` → 结构化比赛数据
4. 网页 → `fetch_odds` → 网络比赛数据
5. 网络数据 + 小黑盒数据 → `team_match` → 标准化数据
6. 标准化数据 → `DataManager` → SQLite数据库

## 异常处理

系统实现了多种异常处理机制：
- 网络请求失败时，使用本地数据继续处理
- OCR识别失败时，使用默认值或跳过处理
- 界面导航失败时，重试或初始化系统
- 数据处理异常时，记录错误并继续下一项处理

## 配置文件结构

`config.yaml` 包含以下主要配置：
- 模拟器路径和配置
- ADB连接参数
- OCR模型路径
- 要处理的游戏项目和对应URL
- 数据存储路径
- 可能需要跳过的游戏项目

## 数据存储结构

### 数据库文件路径
数据按以下结构存储：
```
data/
└── CS2/                       # 游戏项目目录
    ├── mappings.db           # 存储名称映射关系
    └── blast_spring_2025/    # 比赛目录（使用URL提取的标准化名称）
        ├── matches.db        # 网络数据
        └── lbb_matches.db    # 小黑盒数据
```

### 比赛名称处理
1. 标准化比赛名称
   - 从URL中提取并标准化（如 "blast-premier-spring" -> "blast_spring_2025"）
   - 处理规则：
     * 替换连字符为下划线
     * 转换为小写
     * 移除无关后缀（如二字符数字）
     * 确保包含年份（没有则添加当前年份）

2. OCR识别的比赛名称
   - 从小黑盒界面识别（如 "2025BLAST春季公开赛BO3"）
   - 通过mappings.db映射到标准化名称

### 数据库表结构
1. matches表（同时适用于matches.db和lbb_matches.db）：
```sql
CREATE TABLE matches (
    match_id TEXT PRIMARY KEY,    -- 比赛唯一标识
    match_name TEXT,             -- 比赛名称（标准化后的）
    match_time TEXT,             -- 比赛时间
    team_a TEXT,                -- A队名称
    team_b TEXT,                -- B队名称
    odds_a REAL,                -- A队赔率
    odds_b REAL                 -- B队赔率
)
```

2. mappings.db中的表结构：
```sql
-- 比赛名称映射表
CREATE TABLE match_name_mapping (
    lbb_match_name TEXT,         -- OCR识别的比赛名称
    web_match_name TEXT,         -- URL提取的标准化名称
    game_name TEXT,             -- 游戏名称
    last_updated TEXT,          -- 更新时间
    PRIMARY KEY (lbb_match_name, game_name)
)

-- 队伍名称映射表
CREATE TABLE team_mapping (
    lbb_team TEXT,              -- 小黑盒识别的队伍名称
    web_team TEXT,              -- 网站获取的标准队伍名称
    game_name TEXT,             -- 游戏名称
    last_updated TEXT,          -- 更新时间
    PRIMARY KEY (lbb_team, game_name)
)
```

### 名称映射流程
1. 比赛名称映射：
   - 从URL提取标准化比赛名称
   - OCR识别小黑盒界面获取比赛名称
   - 将两者关系存储在mappings.db中
   - 使用标准化名称创建比赛数据目录

2. 队伍名称映射：
   - 根据比赛时间匹配网站和小黑盒的比赛数据
   - 使用模糊匹配（首字母或相似度）确定队伍对应关系
   - 将映射关系存储在mappings.db中
