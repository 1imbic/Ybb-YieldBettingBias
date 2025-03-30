# data_manager.py
import re
import sqlite3
import os
import logging
from datetime import datetime, timedelta

class DataManager:
    def __init__(self, config):
        self.config = config
        logging.info("DataManager initialized with config: %s", config)

    def parse_extended_time(self, time_str):
        """解析可能超过24小时的时间格式 'H:M:S'"""
        logging.debug("Parsing time string: %s", time_str)
        try:
            h, m, s = map(int, time_str.split(":"))
            days, hours = divmod(h, 24)
            current_time = datetime.now()
            delta = timedelta(days=days, hours=hours, minutes=m, seconds=s)
            result = (current_time + delta).strftime("%Y-%m-%d %H:%M:%S")
            logging.info("Parsed time '%s' to '%s' (days=%d, hours=%d, minutes=%d, seconds=%d)", 
                        time_str, result, days, hours, m, s)
            return result
        except ValueError as e:
            logging.error("Error parsing time '%s': %s", time_str, e)
            default_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("Using default time due to parsing error: %s", default_time)
            return default_time

    def process_text_data(self, text_data):
        """处理文本数据，提取字段，根据x轴坐标从左到右识别队伍和赔率"""
        match_name = None
        filtered_data = []
        
        # 过滤和提取 match_name
        for item in text_data:
            text = item["text"]
            logging.debug("Processing text item: %s", text)
            clean_text = re.sub(r'[^a-zA-Z0-9:]', '', text)
            if "BO" in clean_text.upper() or "B0" in clean_text.upper():
                match_name = re.sub(r'\s+', '', text)
                print(f"[文本处理] 识别到比赛名称: {match_name}")
                continue
            if any(keyword in text for keyword in ["预测中", "猜胜负", "奖励率", "后", "刷新"]):
                continue
            filtered_data.append(item)

        if match_name is None:
            print("[文本处理] 未找到比赛名称，跳过处理")
            return None, None

        try:
            # 分离队伍名称和赔率
            team_items = []
            odds_items = []
            time_items = []
            
            for item in filtered_data:
                text = item["text"]
                x_coord = item["coordinates"][0]
                
                if "." in text and text.replace(".", "").isdigit():
                    odds_items.append({"text": float(text), "x": x_coord})
                elif ":" in text:
                    time_items.append({"text": text, "x": x_coord})
                else:
                    if text.strip() and text not in ["", " "]:
                        team_items.append({"text": str(text), "x": x_coord})
            
            # 根据x坐标排序队伍和赔率
            team_items.sort(key=lambda x: x["x"])
            odds_items.sort(key=lambda x: x["x"])
            
            if len(team_items) < 2 or len(odds_items) < 2:
                print(f"[文本处理] 数据不足 - 队伍: {len(team_items)}, 赔率: {len(odds_items)}")
                return None, None
            
            # 取前两个队伍和赔率，左侧为A，右侧为B
            team_a = team_items[0]["text"]
            team_b = team_items[1]["text"]
            odds_a = odds_items[0]["text"]
            odds_b = odds_items[1]["text"]
            match_time = self.parse_extended_time(time_items[0]["text"]) if time_items else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            processed_data = {
                "team_a": team_a,
                "team_b": team_b,
                "odds_a": odds_a,
                "odds_b": odds_b,
                "time": match_time,
                "match_name": match_name
            }
            
            print(f"[文本处理] 处理结果: {team_a}({odds_a}) vs {team_b}({odds_b}), 时间: {match_time}")
            
        except (ValueError, IndexError) as e:
            print(f"[文本处理] 处理失败: {str(e)}")
            return None, None

        return match_name, processed_data

    def save_to_sqlite(self, event_name, match_name, data, match_id=None):
        """保存数据到 SQLite 文件，将小黑盒数据保存到lbb_matches.db，完全隔离于web_matches.db"""
        print(f"[数据保存] 开始保存小黑盒数据: 事件='{event_name}', 比赛='{match_name}'")
        
        if not data or not match_name:
            print("[数据保存] 没有数据或比赛名称，跳过")
            return None

        # 如果数据中包含原始名称，优先使用它查询映射
        original_match_name = data.get("original_match_name", match_name)
        
        # 清理比赛名称中的非法字符，以便用作目录名
        safe_match_name = re.sub(r'[<>:"/\\|?*]', '_', match_name)
        
        # 构建存储路径: data/CS2/比赛名字/
        match_data_dir = self.config['fetch']['data_dir']
        game_folder = os.path.join(match_data_dir, event_name)
        os.makedirs(game_folder, exist_ok=True)
        
        # 检查映射关系以决定如何保存数据
        mapping_found = False
        mapped_name = None
        db_path = os.path.join(game_folder, 'mappings.db')
        
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 首先查询原始名称的映射
            cursor.execute('SELECT web_match_name FROM match_name_mapping WHERE lbb_match_name = ? AND game_name = ?', 
                         (original_match_name, event_name))
            mapping = cursor.fetchone()
            
            if mapping and mapping[0] and not mapping[0].startswith("UNMATCHED_") and not mapping[0] == "TIME_DIFF_TOO_LARGE":
                mapped_name = mapping[0]
                mapping_found = True
                print(f"[数据保存] 找到有效映射: {original_match_name} -> {mapped_name}")
            else:
                # 如果原始名称没有映射，检查标准化名称是否已经是标准名称
                cursor.execute('SELECT 1 FROM match_name_mapping WHERE web_match_name = ? AND game_name = ?', 
                            (match_name, event_name))
                is_standard_name = cursor.fetchone() is not None
                
                if is_standard_name:
                    mapped_name = match_name
                    mapping_found = True
                    print(f"[数据保存] 使用标准化名称: {match_name}")
                else:
                    print(f"[数据保存] 未找到映射，使用默认路径保存: {match_name}")
            
            conn.close()
        
        # 确定目标文件夹
        if mapping_found and mapped_name:
            # 使用映射的标准名称作为目录
            safe_match_name = re.sub(r'[<>:"/\\|?*]', '_', mapped_name)
            match_folder = os.path.join(game_folder, safe_match_name)
        else:
            # 直接使用传入的match_name作为目录
            match_folder = os.path.join(game_folder, safe_match_name)
        
        os.makedirs(match_folder, exist_ok=True)
        
        # 获取当前保存时间
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 保存原始数据
        original_team_a = data.get("original_team_a", data["team_a"])
        original_team_b = data.get("original_team_b", data["team_b"])
        
        # 先在lbb_matches.db中检查是否有相似比赛（通过队伍和时间）
        lbb_db_path = os.path.join(match_folder, "lbb_matches.db")
        if os.path.exists(lbb_db_path):
            conn = sqlite3.connect(lbb_db_path)
            cursor = conn.cursor()
            
            # 提取比赛日期用于模糊匹配
            match_date = data["time"].split(" ")[0]  # 只使用日期部分，如 "2023-05-20"
            
            # 查询有没有同一天同两支队伍的比赛（忽略队伍顺序）
            cursor.execute("""
                SELECT match_id FROM matches 
                WHERE match_time LIKE ? AND 
                      ((team_a = ? AND team_b = ?) OR 
                       (team_a = ? AND team_b = ?))
            """, (f"{match_date}%", data["team_a"], data["team_b"], 
                  data["team_b"], data["team_a"]))
            
            match_row = cursor.fetchone()
            if match_row and match_id is None:
                match_id = match_row[0]
                print(f"[数据保存] 找到时间和队伍匹配的记录，使用其ID: {match_id}")
            
            conn.close()
        
        # 生成唯一ID如果仍未提供或找到
        if match_id is None:
            match_id = f"lbb_{event_name}_{safe_match_name}_{data['time'].replace(':', '').replace(' ', '')}"
            print(f"[数据保存] 生成新LBB数据ID: {match_id}")
        
        # 无论如何，保存小黑盒数据到lbb_matches.db
        conn = sqlite3.connect(lbb_db_path)
        cursor = conn.cursor()
        
        # 确保表结构包含last_updated字段
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                match_name TEXT,
                match_time TEXT,
                team_a TEXT,
                team_b TEXT,
                odds_a REAL,
                odds_b REAL,
                original_match_name TEXT,
                original_team_a TEXT,
                original_team_b TEXT,
                last_updated TEXT
            )
        """)
        
        cursor.execute("SELECT match_id FROM matches WHERE match_id = ?", (match_id,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE matches SET 
                    odds_a = ?, odds_b = ?, match_time = ?, match_name = ?, 
                    team_a = ?, team_b = ?, original_match_name = ?,
                    original_team_a = ?, original_team_b = ?, last_updated = ?
                WHERE match_id = ?
            """, (data["odds_a"], data["odds_b"], data["time"], match_name, 
                 data["team_a"], data["team_b"], original_match_name,
                 original_team_a, original_team_b, now, match_id))
            print(f"[数据保存] 更新LBB记录: {match_id}")
        else:
            cursor.execute("""
                INSERT INTO matches (
                    match_id, match_name, match_time, team_a, team_b, 
                    odds_a, odds_b, original_match_name, original_team_a, 
                    original_team_b, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (match_id, match_name, data["time"], data["team_a"], data["team_b"], 
                 data["odds_a"], data["odds_b"], original_match_name, 
                 original_team_a, original_team_b, now))
            print(f"[数据保存] 创建新LBB记录: {match_id}")
        
        conn.commit()
        conn.close()
        print(f"[数据保存] 完成LBB数据保存: {match_name}")
        
        # 如果没有找到映射，则还需要保存到默认数据库
        if not mapping_found:
            default_db_path = os.path.join(game_folder, "default_lbb_matches.db")
            conn = sqlite3.connect(default_db_path)
            cursor = conn.cursor()
            
            # 确保表结构包含last_updated字段
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    match_id TEXT PRIMARY KEY,
                    match_name TEXT,
                    match_time TEXT,
                    team_a TEXT,
                    team_b TEXT,
                    odds_a REAL,
                    odds_b REAL,
                    original_match_name TEXT,
                    original_team_a TEXT,
                    original_team_b TEXT,
                    creation_time TEXT,
                    last_updated TEXT
                )
            """)
            
            # 检查是否已存在记录
            cursor.execute("SELECT match_id FROM matches WHERE match_id = ?", (match_id,))
            existing = cursor.fetchone()
            
            # 如果未找到精确匹配，尝试查找相似记录
            if not existing:
                match_date = data["time"].split(" ")[0]
                cursor.execute("""
                    SELECT match_id FROM matches 
                    WHERE match_time LIKE ? AND 
                          ((team_a = ? AND team_b = ?) OR 
                           (team_a = ? AND team_b = ?))
                """, (f"{match_date}%", data["team_a"], data["team_b"], 
                      data["team_b"], data["team_a"]))
                similar_match = cursor.fetchone()
                if similar_match:
                    existing = similar_match
                    print(f"[数据保存] 找到相似的默认数据库记录: {existing[0]}")
            
            if existing:
                # 更新已有记录
                cursor.execute("""
                    UPDATE matches SET 
                        odds_a = ?, odds_b = ?, match_time = ?, match_name = ?, 
                        team_a = ?, team_b = ?, original_match_name = ?,
                        original_team_a = ?, original_team_b = ?, last_updated = ?
                    WHERE match_id = ?
                """, (data["odds_a"], data["odds_b"], data["time"], match_name, 
                     data["team_a"], data["team_b"], original_match_name,
                     original_team_a, original_team_b, now, existing[0]))
                print(f"[数据保存] 更新默认数据库记录: {existing[0]}")
            else:
                # 插入新记录
                cursor.execute("""
                    INSERT INTO matches (
                        match_id, match_name, match_time, team_a, team_b, 
                        odds_a, odds_b, original_match_name, original_team_a, 
                        original_team_b, creation_time, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (match_id, match_name, data["time"], data["team_a"], data["team_b"], 
                     data["odds_a"], data["odds_b"], original_match_name, 
                     original_team_a, original_team_b, now, now))
                print(f"[数据保存] 创建新默认数据库记录: {match_id}")
            
            conn.commit()
            conn.close()
            print(f"[数据保存] 完成默认数据库处理: {event_name}/default_lbb_matches.db")
        
        return match_id