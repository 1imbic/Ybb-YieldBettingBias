# fetch_odds.py
import os
import sqlite3
import time
from datetime import datetime, timedelta
from cachetools import TTLCache
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import logging

# 配置缓存
cache = TTLCache(maxsize=100, ttl=600)

def extract_match_name(url):
    """从URL中提取比赛名称"""
    parts = url.split('/')
    if 'tournament' in parts:
        index = parts.index('tournament')
        if index + 1 < len(parts):
            full_name = parts[index + 1].replace('-', '_')
            name_parts = full_name.split('_')
            while name_parts and len(name_parts[-1]) == 2 and name_parts[-1].isdigit():
                name_parts.pop()
            if name_parts and name_parts[-1] == "in" and len(name_parts) > 1 and name_parts[-2] == "play":
                name_parts = name_parts[:-2]
            return '_'.join(name_parts)
    return "unknown_match"

def parse_time_element(time_div):
    """解析时间元素，支持多种格式并返回标准时间字符串"""
    try:
        time_parts = time_div.find_elements(By.TAG_NAME, 'div')
        if len(time_parts) < 2:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None
        
        part1 = time_parts[0].text.strip()
        part2 = time_parts[1].text.strip()
        
        if part1.startswith("BO"):
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S'), f"{part1} {part2}"
        
        time_str = part1
        date_str = part2
        current_year = datetime.now().year
        
        if date_str == "今天":
            date = datetime.now().strftime('%Y-%m-%d')
        elif date_str == "明天":
            date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        elif "月" in date_str:
            month, day = date_str.replace("月", "").split()
            date = f"{current_year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None
        
        full_time_str = f"{date} {time_str}:00"
        return datetime.strptime(full_time_str, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S'), None
    except Exception as e:
        logging.warning(f"时间解析失败: {e}")
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None

def adjust_odds(odds_text):
    """调整赔率格式"""
    return '1.01' if odds_text == '-' else odds_text

def setup_driver():
    """配置并返回Selenium WebDriver"""
    options = Options()
    options.headless = True
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    options.add_argument('--log-level=3')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as e:
        logging.error(f"WebDriver 初始化失败: {e}")
        return None

def fetch_team_odds(config, urls=None, force_refresh=False, max_attempts=3):
    """抓取队伍赔率数据"""
    if urls is None:
        urls = config['urls']['games']
    all_new_matches = []

    for game_name, url in urls.items():
        logging.info(f"[{game_name}] 开始抓取数据，URL: {url}, Force Refresh: {force_refresh}")
        
        # 检查缓存
        if not force_refresh and url in cache:
            logging.info(f"[{game_name}] 使用缓存数据")
            all_new_matches.extend(cache[url])
            continue

        match_name = extract_match_name(url)
        match_folder = os.path.join(config['fetch']['data_dir'], game_name, match_name)
        os.makedirs(match_folder, exist_ok=True)
        db_path = os.path.join(match_folder, 'matches.db')

        # 初始化数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            match_name TEXT,
            match_time TEXT,
            team_a TEXT,
            team_b TEXT,
            odds_a TEXT,
            odds_b TEXT
        )''')
        conn.commit()

        driver = setup_driver()
        if not driver:
            conn.close()
            return -1, None, "WebDriver 初始化失败"

        attempt = 0
        success = False
        while attempt < max_attempts and not success:
            attempt += 1
            logging.info(f"[{game_name}] 尝试第 {attempt}/{max_attempts} 次加载页面")
            try:
                driver.get(url)
                WebDriverWait(driver, 60).until(
                    EC.presence_of_all_elements_located((By.TAG_NAME, "body"))
                )

                page_source = driver.page_source
                if '<h1' in page_source and 'Error' in page_source and '1000' in page_source:
                    logging.error(f"[{game_name}] 检测到 Error 1000")
                    return -1, None, "Error 1000 detected"

                odd_buttons = driver.find_elements(By.CSS_SELECTOR, '[data-test^="odd-button"]')
                time_elements = driver.find_elements(By.CSS_SELECTOR, 'div.text-sm.text-grey-500, div.text-sm.text-grey-500.opacity-100')
                logging.info(f"[{game_name}] 找到 {len(odd_buttons)} 个赔率按钮，{len(time_elements)} 个时间元素")

                match_data = {}
                for button in odd_buttons:
                    try:
                        data_label = button.get_attribute('data-label')
                        if not data_label or '~' not in data_label:
                            continue
                        parts = data_label.split('~')
                        if len(parts) != 3 or parts[1] != '1':
                            continue
                        match_id, _, team_index = parts

                        team_name = button.find_element(By.CSS_SELECTOR, '[data-test="odd-button__title"]').text.strip()
                        odds_text = adjust_odds(button.find_element(By.CSS_SELECTOR, '[data-test="odd-button__result"]').text.strip())

                        if match_id not in match_data:
                            match_data[match_id] = {"team_a": None, "team_b": None, "team_a_odds": None, "team_b_odds": None}
                        if team_index == '1':
                            match_data[match_id]["team_a"] = team_name
                            match_data[match_id]["team_a_odds"] = odds_text
                        elif team_index == '2':
                            match_data[match_id]["team_b"] = team_name
                            match_data[match_id]["team_b_odds"] = odds_text
                    except Exception as e:
                        logging.warning(f"[{game_name}] 处理赔率按钮时出错: {e}")

                if not match_data:
                    logging.warning(f"[{game_name}] 无有效数据")
                    continue

                new_matches = []
                for i, (match_id, data) in enumerate(match_data.items()):
                    time_div = time_elements[i] if i < len(time_elements) else None
                    match_time, special_info = parse_time_element(time_div) if time_div else (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None)
                    if special_info and "BO" in special_info:
                        continue

                    if not all([data["team_a"], data["team_b"], data["team_a_odds"], data["team_b_odds"]]):
                        logging.warning(f"[{game_name}] 跳过不完整数据: {match_id}")
                        continue

                    cursor.execute("SELECT match_id FROM matches WHERE match_id = ?", (match_id,))
                    if cursor.fetchone():
                        cursor.execute('''UPDATE matches SET match_name = ?, match_time = ?, team_a = ?, team_b = ?, odds_a = ?, odds_b = ?
                            WHERE match_id = ?''', (match_name, match_time, data["team_a"], data["team_b"], data["team_a_odds"], data["team_b_odds"], match_id))
                        logging.debug(f"[{game_name}] 更新比赛数据: {match_id}")
                    else:
                        cursor.execute('''INSERT INTO matches (match_id, match_name, match_time, team_a, team_b, odds_a, odds_b)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''', (match_id, match_name, match_time, data["team_a"], data["team_b"], data["team_a_odds"], data["team_b_odds"]))
                        logging.debug(f"[{game_name}] 插入新比赛数据: {match_id}")
                        new_matches.append({
                            "MatchID": match_id,
                            "MatchName": match_name,
                            "MatchTime": match_time,
                            "TeamA": data["team_a"],
                            "TeamB": data["team_b"],
                            "TeamA_Odds": data["team_a_odds"],
                            "TeamB_Odds": data["team_b_odds"]
                        })

                conn.commit()
                cache[url] = new_matches
                all_new_matches.extend(new_matches)
                success = True
                logging.info(f"[{game_name}] 数据抓取成功，新增 {len(new_matches)} 场比赛")

            except TimeoutException:
                logging.error(f"[{game_name}] 第 {attempt} 次页面加载超时")
                if attempt < max_attempts:
                    time.sleep(5)  # 重试前等待
            except Exception as e:
                logging.error(f"[{game_name}] 第 {attempt} 次抓取失败: {e}")
                if attempt < max_attempts:
                    time.sleep(5)

        driver.quit()
        conn.close()
        if not success:
            logging.error(f"[{game_name}] 经过 {max_attempts} 次尝试仍失败")
            return -1, None, f"Failed after {max_attempts} attempts"

    return 0, all_new_matches