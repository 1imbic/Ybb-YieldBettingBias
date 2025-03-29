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

# 配置缓存：用于存储网络请求结果，减少重复请求
cache = TTLCache(maxsize=100, ttl=600)  # 缓存大小100条，有效期600秒

def extract_match_name(url):
    """从URL中提取比赛名称，用于标识比赛"""
    parts = url.split('/')
    if 'tournament' in parts:
        index = parts.index('tournament')
        if index + 1 < len(parts):
            # 提取比赛名称并进行标准化处理
            full_name = parts[index + 1].replace('-', '_').lower()
            name_parts = full_name.split('_')
            
            # 移除无关的后缀
            while name_parts and len(name_parts[-1]) == 2 and name_parts[-1].isdigit():
                name_parts.pop()
            if name_parts and name_parts[-1] == "in" and len(name_parts) > 1 and name_parts[-2] == "play":
                name_parts = name_parts[:-2]
                
            # 确保包含年份，如果没有则添加当前年份
            has_year = any(part.isdigit() and len(part) == 4 for part in name_parts)
            if not has_year:
                current_year = str(datetime.now().year)
                name_parts.insert(0, current_year)
                
            # 构建最终的标准化名称
            standard_name = '_'.join(name_parts)
            print(f"[网络] 从URL提取的标准化比赛名称: {standard_name}")
            return standard_name
            
    print("[网络] 无法从URL提取比赛名称，使用默认名称")
    return "unknown_match"

def parse_time_element(time_div):
    """解析网页上的时间元素，支持多种格式并返回标准时间字符串"""
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
        print(f"[网络] 时间解析失败: {e}")
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None

def adjust_odds(odds_text):
    """调整赔率格式，将'-'转换为最小赔率'1.01'"""
    return '1.01' if odds_text == '-' else odds_text

def setup_driver():
    """配置并返回Selenium WebDriver，用于自动控制浏览器获取数据"""
    options = Options()
    options.headless = True  # 无头模式，不显示浏览器界面
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    options.add_argument('--log-level=3')  # 最小化日志输出
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    try:
        print("[网络] 初始化Chrome WebDriver")
        return webdriver.Chrome(options=options)
    except WebDriverException as e:
        print(f"[网络] WebDriver初始化失败: {e}")
        return None

def fetch_team_odds(config, urls=None, force_refresh=False, max_attempts=3):
    """
    从网络获取比赛赔率数据:
    1. 使用Selenium访问网页获取比赛信息
    2. 提取队伍名称、赔率和比赛时间
    3. 将数据保存到SQLite数据库
    4. 返回新获取的比赛数据
    """
    if urls is None:
        urls = config['urls']['games']
    all_new_matches = []

    for game_name, url in urls.items():
        print(f"[网络] [{game_name}] 开始抓取数据，URL: {url}, 强制刷新: {force_refresh}")
        
        # 检查缓存，减少重复请求
        if not force_refresh and url in cache:
            print(f"[网络] [{game_name}] 使用缓存数据")
            all_new_matches.extend(cache[url])
            continue

        # 创建数据存储目录和数据库
        match_name = extract_match_name(url)
        # 构建存储路径: data/CS2/比赛名字/
        game_folder = os.path.join(config['fetch']['data_dir'], game_name)
        os.makedirs(game_folder, exist_ok=True)
        
        # 创建比赛名称对应的目录
        match_folder = os.path.join(game_folder, match_name)
        os.makedirs(match_folder, exist_ok=True)
        
        # 数据库文件路径
        db_path = os.path.join(match_folder, "matches.db")
        print(f"[网络] [{game_name}] 数据库路径: {db_path}")

        # 初始化数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            match_name TEXT,
            match_time TEXT,
            team_a TEXT,
            team_b TEXT,
            odds_a REAL,
            odds_b REAL
        )''')
        conn.commit()

        # 初始化WebDriver
        driver = setup_driver()
        if not driver:
            conn.close()
            return -1, None

        # 重试机制，最多尝试max_attempts次
        attempt = 0
        success = False
        while attempt < max_attempts and not success:
            attempt += 1
            print(f"[网络] [{game_name}] 尝试第 {attempt}/{max_attempts} 次加载页面")
            try:
                # 加载页面
                driver.get(url)
                print(f"[网络] [{game_name}] 等待页面加载，超时时间: 60秒")
                WebDriverWait(driver, 60).until(
                    EC.presence_of_all_elements_located((By.TAG_NAME, "body"))
                )
                # 延长等待时间，确保动态内容加载完成
                print(f"[网络] [{game_name}] 页面基本元素已加载，额外等待10秒确保动态内容加载")
                time.sleep(10)

                # 检查页面错误
                page_source = driver.page_source
                if '<h1' in page_source and 'Error' in page_source and '1000' in page_source:
                    print(f"[网络] [{game_name}] 检测到 Error 1000")
                    return -1, None

                # 查找赔率按钮和时间元素
                odd_buttons = driver.find_elements(By.CSS_SELECTOR, '[data-test^="odd-button"]')
                time_elements = driver.find_elements(By.CSS_SELECTOR, 'div.text-sm.text-grey-500, div.text-sm.text-grey-500.opacity-100')
                print(f"[网络] [{game_name}] 找到 {len(odd_buttons)} 个赔率按钮，{len(time_elements)} 个时间元素")
                
                # 详细打印时间元素内容
                if time_elements:
                    print(f"[网络] [{game_name}] 时间元素详情:")
                    for i, time_elem in enumerate(time_elements):
                        try:
                            text = time_elem.text.strip()
                            print(f"[网络] [{game_name}] - 时间元素 {i+1}: '{text}'")
                        except:
                            print(f"[网络] [{game_name}] - 时间元素 {i+1}: 无法获取文本")
                else:
                    print(f"[网络] [{game_name}] 未找到任何时间元素")
                
                # 详细打印赔率按钮信息
                if odd_buttons:
                    print(f"[网络] [{game_name}] 赔率按钮详情:")
                    data_labels = set()
                    for i, button in enumerate(odd_buttons[:5]):  # 只打印前5个按钮以避免过多日志
                        try:
                            label = button.get_attribute('data-label')
                            title = button.find_element(By.CSS_SELECTOR, '[data-test="odd-button__title"]').text.strip()
                            result = button.find_element(By.CSS_SELECTOR, '[data-test="odd-button__result"]').text.strip()
                            print(f"[网络] [{game_name}] - 按钮 {i+1}: 标签='{label}', 标题='{title}', 结果='{result}'")
                            if label:
                                data_labels.add(label.split('~')[0] if '~' in label else label)
                        except Exception as e:
                            print(f"[网络] [{game_name}] - 按钮 {i+1}: 获取信息失败: {e}")
                    print(f"[网络] [{game_name}] 找到 {len(data_labels)} 个不同的比赛ID: {data_labels}")
                else:
                    print(f"[网络] [{game_name}] 未找到任何赔率按钮")

                # 处理赔率按钮，提取队伍和赔率
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
                        print(f"[网络] [{game_name}] 处理赔率按钮时出错: {e}")

                # 分析匹配结果
                print(f"[网络] [{game_name}] 处理完成，获取到 {len(match_data)} 个比赛数据")
                for match_id, data in match_data.items():
                    print(f"[网络] [{game_name}] - 比赛ID: {match_id}")
                    print(f"[网络] [{game_name}]   队伍A: {data['team_a']}, 赔率: {data['team_a_odds']}")
                    print(f"[网络] [{game_name}]   队伍B: {data['team_b']}, 赔率: {data['team_b_odds']}")
                
                if not match_data:
                    print(f"[网络] [{game_name}] 无有效数据")
                    print(f"[网络] [{game_name}] 尝试分析页面结构以查找问题")
                    try:
                        # 尝试其他选择器
                        alternative_buttons = driver.find_elements(By.CSS_SELECTOR, '.odd-button')
                        print(f"[网络] [{game_name}] 替代选择器找到 {len(alternative_buttons)} 个按钮")
                        
                        # 检查页面主要内容
                        main_content = driver.find_elements(By.CSS_SELECTOR, 'main')
                        print(f"[网络] [{game_name}] 页面主要内容区域数量: {len(main_content)}")
                        
                        # 检查是否有加载动画
                        loaders = driver.find_elements(By.CSS_SELECTOR, '.loader, .loading, .spinner')
                        if loaders:
                            print(f"[网络] [{game_name}] 发现 {len(loaders)} 个加载指示器，页面可能未加载完成")
                        
                        # 截取一部分HTML用于调试
                        html_sample = driver.page_source[:1000] + "..." if len(driver.page_source) > 1000 else driver.page_source
                        print(f"[网络] [{game_name}] 页面HTML样本: {html_sample}")
                    except Exception as e:
                        print(f"[网络] [{game_name}] 分析页面结构时出错: {e}")
                    continue

                # 处理每个比赛数据
                new_matches = []
                for i, (match_id, data) in enumerate(match_data.items()):
                    time_div = time_elements[i] if i < len(time_elements) else None
                    match_time, special_info = parse_time_element(time_div) if time_div else (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None)
                    if special_info and "BO" in special_info:
                        continue

                    # 检查数据完整性
                    if not all([data["team_a"], data["team_b"], data["team_a_odds"], data["team_b_odds"]]):
                        print(f"[网络] [{game_name}] 跳过不完整数据: {match_id}")
                        continue

                    # 保存到数据库
                    cursor.execute("SELECT match_id FROM matches WHERE match_id = ?", (match_id,))
                    if cursor.fetchone():
                        cursor.execute('''UPDATE matches SET match_name = ?, match_time = ?, team_a = ?, team_b = ?, odds_a = ?, odds_b = ?
                            WHERE match_id = ?''', (match_name, match_time, data["team_a"], data["team_b"], float(data["team_a_odds"]), float(data["team_b_odds"]), match_id))
                        print(f"[网络] [{game_name}] 更新比赛数据: {match_id}")
                    else:
                        cursor.execute('''INSERT INTO matches (match_id, match_name, match_time, team_a, team_b, odds_a, odds_b)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''', (match_id, match_name, match_time, data["team_a"], data["team_b"], float(data["team_a_odds"]), float(data["team_b_odds"])))
                        print(f"[网络] [{game_name}] 插入新比赛数据: {match_id}")
                        # 添加到新比赛列表
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
                cache[url] = new_matches  # 更新缓存
                all_new_matches.extend(new_matches)
                success = True
                print(f"[网络] [{game_name}] 数据抓取成功，新增 {len(new_matches)} 场比赛")

            except TimeoutException:
                print(f"[网络] [{game_name}] 第 {attempt} 次页面加载超时")
                if attempt < max_attempts:
                    time.sleep(5)  # 重试前等待
            except Exception as e:
                print(f"[网络] [{game_name}] 第 {attempt} 次抓取失败: {e}")
                if attempt < max_attempts:
                    time.sleep(5)

        driver.quit()
        conn.close()
        if not success:
            print(f"[网络] [{game_name}] 经过 {max_attempts} 次尝试仍失败")
            return -1, None

    return 0, all_new_matches