# 小黑盒赔率收集系统流程分析

## 项目概述

本项目是一个自动化数据收集系统，用于从小黑盒应用中获取电子竞技比赛的赔率数据。系统通过模拟器运行小黑盒应用，使用OCR技术识别界面内容，并与网络数据源进行匹配和整合。收集的数据经过处理后，可用于计算凯利公式和投注建议。

## 模块依赖关系

```
main.py
  ├── init_manager.py
  ├── screen_manager.py
  ├── data_manager.py
  ├── fetch_odds.py
  ├── team_match.py
  └── kelly_calculator.py
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
- **数据存储**：将处理后的小黑盒数据保存到lbb_matches.db，与web数据完全隔离
- **原始数据保留**：保存原始数据以便追踪和调试

主要调用流程：
1. `process_text_data()`：处理OCR文本，提取结构化信息
2. `parse_extended_time()`：解析时间信息
3. `save_to_sqlite()`：将小黑盒数据仅保存到lbb_matches.db

输入：OCR提取的文本数据
输出：结构化的比赛数据，并根据匹配状态存储到不同数据库中

### 4. 网络数据获取 (fetch_odds)

`fetch_odds.py` 负责从网络获取比赛信息和赔率：

- **浏览器自动化**：使用Selenium控制浏览器访问网页
- **数据提取**：从网页解析比赛信息、队伍名称和赔率
- **数据存储**：将网络数据保存到SQLite数据库web_matches.db，标记来源为"web"
- **缓存机制**：使用TTLCache缓存请求结果，减少重复请求
- **优化输出**：减少调试信息，汇总打印比赛数据

主要函数 `fetch_team_odds()` 完成从配置的URL获取比赛数据的工作，失败时系统会尝试使用本地数据。网络数据被视为权威数据源，且仅保存在web_matches.db中与小黑盒数据完全隔离。

输入：配置信息、URLs
输出：网络获取的比赛数据或本地加载的备用数据

### 5. 团队匹配 (team_match)

`team_match.py` 负责匹配来自不同来源的队伍和比赛名称：

- **初始化数据库**：创建或连接映射数据库
- **队伍规范化**：去除前缀（如"Team"）并统一格式
- **增强匹配算法**：支持多种匹配方式，包括首字母匹配、规范化匹配、包含关系匹配和相似度匹配
- **记录匹配结果**：包括成功匹配和失败匹配，便于后续分析
- **保留原始数据**：在数据替换过程中保留原始名称，便于追踪

主要函数：
- `fuzzy_match()`：增强的模糊匹配算法，支持多种匹配策略
- `match_teams_and_names()`：尝试匹配队伍和比赛名称，并将结果存入映射数据库
- `replace_team_and_match_name()`：根据映射关系替换原始名称，并保留原始数据

输入：网络数据、小黑盒数据
输出：名称映射关系和替换后的数据，包含原始数据引用

### 6. 凯利计算器 (kelly_calculator)

`kelly_calculator.py` 负责基于收集的赔率数据计算凯利值和投注建议：

- **数据库读取**：从web_matches.db和lbb_matches.db读取两个来源的比赛和赔率数据
- **比赛匹配**：基于比赛/队伍识别信息匹配来自不同来源的同一比赛数据
- **凯利计算**：使用凯利公式计算最优投注比例
- **COINS计算**：根据凯利值计算投注金额建议
- **结果存储**：将计算结果保存到kelly_results.db

主要函数：
- `calculate_kelly()`：实现凯利公式 f* = (bp - q) / b，计算凯利值
- `calculate_coins()`：基于凯利值计算投注金额建议
- `get_match_data()`：从两个隔离的数据库中读取和匹配比赛数据
- `save_kelly_data()`：将计算结果保存到数据库

计算规则：
- 凯利值范围限制在0到0.5之间
- 凯利值低于0.02的投注机会被忽略
- COINS = (凯利值 - 0.02) * 200，并四舍五入到最近的百位

输入：两个独立数据库中的比赛赔率数据
输出：凯利值和COINS值，保存到kelly_results.db

### 7. 主流程 (main.py)

`main.py` 协调整个系统的运行：

1. **加载配置**：读取 `config.yaml` 配置文件
2. **初始化系统**：调用 `InitManager` 初始化模拟器、ADB和OCR
3. **导航到比赛界面**：通过 `ScreenManager` 导航到赛事中心
4. **循环处理游戏项目**：对配置中的每个游戏项目执行以下步骤：
   - 获取网络数据（`fetch_team_odds`）至web_matches.db
   - 获取小黑盒界面数据（`fetch_lbb_data`）
   - 匹配队伍和比赛名称（`match_teams_and_names`）
   - 替换标准化名称并保留原始数据（`replace_team_and_match_name`）
   - 保存小黑盒数据到lbb_matches.db（`save_to_sqlite`）
5. **计算凯利值**：收集完数据后，可以运行 `kelly_calculator.py` 计算凯利值和投注建议

## 数据流向

1. 配置文件 → `InitManager` → 系统初始化
2. 模拟器界面 → `ScreenManager` → OCR文本数据
3. OCR文本数据 → `DataManager` → 结构化比赛数据 → lbb_matches.db
4. 网页 → `fetch_odds` → 网络比赛数据 → web_matches.db
5. 网络数据 + 小黑盒数据 → `team_match` → 标准化数据（含原始数据引用）
6. 两个隔离数据库数据 → `KellyCalculator` → 凯利值和COINS投注建议

## 异常处理

系统实现了多种异常处理机制：
- 网络请求失败时尝试重试或加载缓存数据
- OCR识别失败时，使用默认值或跳过处理
- 界面导航失败时，重试或初始化系统
- 数据处理异常时，记录错误并继续下一项处理
- 匹配失败时，使用特殊前缀标记数据，便于后续分析
- 凯利计算时，使用日志记录异常并跳过有问题的数据

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
    ├── mappings.db            # 存储名称映射关系
    ├── default_lbb_matches.db # 未匹配成功的小黑盒数据
    ├── kelly_results.db       # 凯利计算结果
    └── blast_spring_2025/     # 比赛目录（使用URL提取的标准化名称）
        ├── web_matches.db     # 网络数据（严格隔离）
        └── lbb_matches.db     # 小黑盒数据（严格隔离）
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
   - 即使匹配失败，也保留原始名称用于追踪

### 数据库表结构

1. web_matches.db表结构：
```sql
CREATE TABLE matches (
    match_id TEXT PRIMARY KEY,    -- 比赛唯一标识（使用web_前缀）
    match_name TEXT,             -- 比赛名称（标准化后的）
    match_time TEXT,             -- 比赛时间
    team_a TEXT,                -- A队名称（标准化后的）
    team_b TEXT,                -- B队名称（标准化后的）
    odds_a REAL,                -- A队赔率
    odds_b REAL,                -- B队赔率
    source TEXT                 -- 数据来源标记（固定为"web"）
)
```

2. lbb_matches.db表结构：
```sql
CREATE TABLE matches (
    match_id TEXT PRIMARY KEY,     -- 比赛唯一标识（使用lbb_前缀）
    match_name TEXT,              -- 比赛名称（标准化后的）
    match_time TEXT,              -- 比赛时间
    team_a TEXT,                 -- A队名称（标准化后的）
    team_b TEXT,                 -- B队名称（标准化后的）
    odds_a REAL,                 -- A队赔率
    odds_b REAL,                 -- B队赔率
    original_match_name TEXT,     -- 原始比赛名称
    original_team_a TEXT,        -- 原始A队名称
    original_team_b TEXT,        -- 原始B队名称
    last_updated TEXT            -- 最近更新时间
)
```

3. default_lbb_matches.db表结构：
```sql
CREATE TABLE matches (
    match_id TEXT PRIMARY KEY,      -- 比赛唯一标识
    match_name TEXT,               -- 比赛名称
    match_time TEXT,               -- 比赛时间
    team_a TEXT,                  -- A队名称
    team_b TEXT,                  -- B队名称
    odds_a REAL,                  -- A队赔率
    odds_b REAL,                  -- B队赔率
    original_match_name TEXT,      -- 原始比赛名称
    original_team_a TEXT,         -- 原始A队名称
    original_team_b TEXT,         -- 原始B队名称
    creation_time TEXT,           -- 创建时间
    last_updated TEXT             -- 最近更新时间
)
```

4. kelly_results.db表结构：
```sql
CREATE TABLE kelly_results (
    match_id TEXT PRIMARY KEY,     -- 比赛唯一标识
    match_name TEXT,              -- 比赛名称
    match_time TEXT,              -- 比赛时间
    team_a TEXT,                 -- A队名称
    team_b TEXT,                 -- B队名称
    web_odds_a REAL,             -- 网站A队赔率
    web_odds_b REAL,             -- 网站B队赔率
    lbb_odds_a REAL,             -- 小黑盒A队赔率
    lbb_odds_b REAL,             -- 小黑盒B队赔率
    kelly_a REAL,                -- A队凯利值
    kelly_b REAL,                -- B队凯利值
    coins_a INTEGER,             -- A队COINS值
    coins_b INTEGER,             -- B队COINS值
    match_dir TEXT,              -- 比赛目录
    calculation_time TEXT        -- 计算时间
)
```

5. mappings.db中的表结构：
```sql
-- 比赛名称映射表
CREATE TABLE match_name_mapping (
    lbb_match_name TEXT,         -- OCR识别的比赛名称
    web_match_name TEXT,         -- URL提取的标准化名称，可能有特殊前缀标记如UNMATCHED_
    game_name TEXT,             -- 游戏名称
    last_updated TEXT,          -- 更新时间
    PRIMARY KEY (lbb_match_name, game_name)
)

-- 队伍名称映射表
CREATE TABLE team_mapping (
    lbb_team TEXT,              -- 小黑盒识别的队伍名称
    web_team TEXT,              -- 网站获取的标准队伍名称，可能有特殊前缀标记如UNCONFIRMED_
    game_name TEXT,             -- 游戏名称
    last_updated TEXT,          -- 更新时间
    PRIMARY KEY (lbb_team, game_name)
)
```

### 数据隔离策略

1. 严格数据隔离：
   - 网络数据和小黑盒数据严格隔离在不同数据库文件中
   - 网络数据仅保存在web_matches.db（表示权威数据源）
   - 小黑盒数据仅保存在lbb_matches.db
   - 两者通过ID前缀（web_/lbb_）避免冲突

2. 小黑盒数据流向：
   - OCR识别 → 文本处理 → 标准化 → lbb_matches.db
   - 匹配失败的数据 → default_lbb_matches.db
   - 严格禁止小黑盒数据写入web_matches.db

3. 网络数据流向：
   - 网络爬取 → 标准化 → web_matches.db
   - 旧的matches.db数据迁移至web_matches.db

4. 凯利计算数据整合：
   - 从两个独立数据库读取数据
   - 基于队伍和比赛名称进行匹配
   - 分别显示和使用两个来源的赔率数据
