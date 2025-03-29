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
        """处理文本数据，提取字段（从 DataProcessor 合并而来）"""
        match_name = None
        filtered_data = []
        
        # 过滤和提取 match_name
        for item in text_data:
            text = item["text"]
            logging.debug("Processing text item: %s", text)
            clean_text = re.sub(r'[^a-zA-Z0-9:]', '', text)
            if "BO" in clean_text.upper() or "B0" in clean_text.upper():
                match_name = re.sub(r'\s+', '', text)
                logging.info("Found match name: %s", match_name)
                continue
            if any(keyword in text for keyword in ["预测中", "猜胜负", "奖励率", "后", "刷新"]):
                logging.debug("Skipping item with keyword: %s", text)
                continue
            filtered_data.append(item)
            logging.debug("Added to filtered data: %s", text)

        if match_name is None:
            logging.warning("No match name found in text data, skipping processing.")
            return None, None

        try:
            # 根据坐标的 y 值排序，确保顺序反映屏幕上的上下位置
            filtered_data.sort(key=lambda x: x["coordinates"][1])  # 假设 coordinates 是 [x, y]

            teams = []
            odds = []
            times = []
            for item in filtered_data:
                text = item["text"]
                if "." in text:
                    odds.append(float(text))
                    logging.debug("Identified odds: %s", text)
                elif ":" in text:
                    times.append(text)
                    logging.debug("Identified time: %s", text)
                else:
                    # 移除长度限制，直接视为队伍，并避免重复
                    if text not in teams and text not in ["", " "]:
                        teams.append(str(text))
                        logging.debug("Identified team: %s", text)

            logging.info("Extracted teams: %s, odds: %s, times: %s", teams, odds, times)

            if len(teams) < 2 or len(odds) < 2:
                logging.warning("Insufficient data - teams: %d (< 2), odds: %d (< 2), skipping.", 
                            len(teams), len(odds))
                return None, None

            # 确保 teams 和 odds 数量匹配，并截取前两个
            teams = teams[:2]
            odds = odds[:2]

            processed_data = {
                "team_a": teams[0],
                "team_b": teams[1],
                "odds_a": odds[0],
                "odds_b": odds[1],
                "time": self.parse_extended_time(times[0]) if times else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "match_name": match_name
            }
            logging.info("Successfully processed data: %s", processed_data)
        except (ValueError, IndexError) as e:
            logging.error("Error processing data: %s", e)
            return None, None

        return match_name, processed_data

    def save_to_sqlite(self, event_name, match_name, data, match_id=None):
        """保存数据到 SQLite 文件，使用独立的 lbb_matches.db"""
        logging.info("Saving data for event '%s', match '%s'", event_name, match_name)
        if not data or not match_name:
            logging.warning("No data or match_name provided, skipping save.")
            return None

        safe_match_name = re.sub(r'[<>:"/\\|?*]', '_', match_name)   
        match_data_dir = self.config['fetch']['data_dir']
        match_folder = os.path.join(match_data_dir, event_name, match_name)
        os.makedirs(match_folder, exist_ok=True)
        db_path = os.path.join(match_folder, "lbb_matches.db")
        logging.info("Database path: %s", db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        logging.debug("Creating table 'matches' if not exists")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                match_name TEXT,
                match_time TEXT,
                team_a TEXT,
                team_b TEXT,
                odds_a REAL,
                odds_b REAL
            )
        """)

        if match_id is None:
            match_id = f"{event_name}_{safe_match_name}_{data['time'].replace(':', '').replace(' ', '')}"
            logging.warning("No match_id provided, generated temporary ID: %s", match_id)

        cursor.execute("SELECT match_id FROM matches WHERE match_id = ?", (match_id,))
        existing = cursor.fetchone()
        if existing:
            logging.info("Match ID %s already exists, updating record", match_id)
            cursor.execute("""
                UPDATE matches SET odds_a = ?, odds_b = ?, match_time = ?, match_name = ?, team_a = ?, team_b = ?
                WHERE match_id = ?
            """, (data["odds_a"], data["odds_b"], data["time"], match_name, data["team_a"], data["team_b"], match_id))
            logging.info("Updated match %s with data: %s", match_id, data)
        else:
            logging.info("Inserting new match with ID: %s", match_id)
            cursor.execute("""
                INSERT INTO matches (match_id, match_name, match_time, team_a, team_b, odds_a, odds_b)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (match_id, match_name, data["time"], data["team_a"], data["team_b"], data["odds_a"], data["odds_b"]))
            logging.info("Inserted new match %s with data: %s", match_id, data)

        conn.commit()
        conn.close()
        logging.info("Database operation completed for %s", db_path)
        return match_id