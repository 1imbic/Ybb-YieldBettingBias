import sqlite3
import os
from datetime import datetime, timedelta
import difflib

def initialize_db(game_folder):
    """初始化数据库连接，创建必要的表"""
    try:
        # 确保目录存在
        os.makedirs(game_folder, exist_ok=True)
        
        # 构建数据库路径
        db_path = os.path.join(game_folder, 'mappings.db')
        print(f"[团队匹配] 数据库路径: {db_path}")
        
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 创建比赛名称映射表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS match_name_mapping (
                lbb_match_name TEXT,
                web_match_name TEXT,
                game_name TEXT,
                last_updated TEXT,
                PRIMARY KEY (lbb_match_name, game_name)
            )
        """)
        
        # 创建队伍名称映射表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS team_mapping (
                lbb_team TEXT,
                web_team TEXT,
                game_name TEXT,
                last_updated TEXT,
                PRIMARY KEY (lbb_team, game_name)
            )
        """)
        
        conn.commit()
        print(f"[团队匹配] 数据库初始化成功: {db_path}")
        return conn, cursor
    except Exception as e:
        print(f"[团队匹配] 数据库初始化失败: {str(e)}")
        raise

def get_initials(team):
    """获取队伍名称的首字母，用于简单匹配"""
    return ''.join(word[0].upper() for word in team.split() if word)

def fuzzy_match(team1, team2, threshold=0.8):
    """
    模糊匹配两个队伍名称：
    1. 如果首字母相同，则认为匹配成功
    2. 否则计算字符串相似度，超过阈值则匹配成功
    """
    initials1, initials2 = get_initials(team1), get_initials(team2)
    if initials1 == initials2:
        print(f"[队伍匹配] 首字母匹配: {team1} -> {team2} ({initials1})")
        return True
    similarity = difflib.SequenceMatcher(None, team1.lower(), team2.lower()).ratio()
    if similarity > threshold:
        print(f"[队伍匹配] 相似度匹配: {team1} -> {team2} ({similarity:.2f})")
        return True
    return False

def match_teams_and_names(web_data, lbb_data, game_name, match_folder):
    """
    匹配队伍和比赛名称：
    1. 使用最新的网络数据中的标准化比赛名称
    2. 检查mappings.db中未匹配的URL比赛名称
    3. 为匹配的比赛创建名称映射关系和match_id映射
    """
    conn, cursor = initialize_db(match_folder)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[名称匹配] 开始处理游戏: {game_name}")

    if not web_data:
        print(f"[名称匹配] 无网络数据，跳过")
        conn.close()
        return

    # 获取最新的网络数据
    web_data = sorted(web_data, key=lambda x: datetime.strptime(x["MatchTime"], '%Y-%m-%d %H:%M:%S'), reverse=True)
    latest_web_match = web_data[0]
    standard_match_name = latest_web_match["MatchName"]
    print(f"[名称匹配] 标准比赛名称: {standard_match_name}")

    # 处理每个OCR识别的比赛
    for lbb_match in lbb_data:
        lbb_match_name = lbb_match["match_name"]
        
        # 检查是否已有映射
        cursor.execute('SELECT web_match_name FROM match_name_mapping WHERE lbb_match_name = ? AND game_name = ?', 
                      (lbb_match_name, game_name))
        existing_mapping = cursor.fetchone()
        
        if not existing_mapping:
            # 保存比赛名称映射
            cursor.execute('INSERT OR REPLACE INTO match_name_mapping (lbb_match_name, web_match_name, game_name, last_updated) VALUES (?, ?, ?, ?)',
                         (lbb_match_name, standard_match_name, game_name, now))
            print(f"[名称匹配] 创建映射: {lbb_match_name} -> {standard_match_name}")

            # 找到时间最接近的网络数据进行队伍匹配
            lbb_time = datetime.strptime(lbb_match["time"], '%Y-%m-%d %H:%M:%S')
            closest_web_match = min(web_data, 
                                  key=lambda x: abs(datetime.strptime(x["MatchTime"], '%Y-%m-%d %H:%M:%S') - lbb_time))
            
            time_diff = abs(datetime.strptime(closest_web_match["MatchTime"], '%Y-%m-%d %H:%M:%S') - lbb_time)
            
            if time_diff <= timedelta(hours=0.5):
                web_teams = [closest_web_match["TeamA"], closest_web_match["TeamB"]]
                lbb_teams = [lbb_match["team_a"], lbb_match["team_b"]]
                
                # 检查队伍是否匹配
                teams_match = all(fuzzy_match(lbb_team, web_team) 
                                for lbb_team, web_team in zip(lbb_teams, web_teams))
                
                if teams_match:
                    # 使用网络数据的match_id
                    lbb_match["match_id"] = closest_web_match.get("MatchId")
                    print(f"[名称匹配] 使用网络match_id: {lbb_match['match_id']}")
                    
                    # 保存队伍映射
                    for lbb_team, web_team in zip(lbb_teams, web_teams):
                        cursor.execute('INSERT OR REPLACE INTO team_mapping (lbb_team, web_team, game_name, last_updated) VALUES (?, ?, ?, ?)',
                                     (lbb_team, web_team, game_name, now))

    conn.commit()
    conn.close()
    print(f"[名称匹配] 完成处理")

def replace_team_and_match_name(lbb_data, game_name, match_folder):
    """
    使用映射替换标准化队伍和比赛名称：
    1. 从映射数据库中查找每个队伍的标准名称
    2. 从映射数据库中查找比赛的标准名称
    3. 用标准名称替换原始名称
    4. 如果没有找到比赛名称映射，返回None表示跳过保存
    """
    conn, cursor = initialize_db(match_folder)
    print(f"[名称替换] 开始处理游戏: {game_name}")
    
    result_data = []
    for match in lbb_data:
        # 替换比赛名
        lbb_match_name = match["match_name"]
        cursor.execute('SELECT web_match_name FROM match_name_mapping WHERE lbb_match_name = ? AND game_name = ?', 
                      (lbb_match_name, game_name))
        match_name_result = cursor.fetchone()
        
        if match_name_result:
            print(f"[名称替换] 比赛: {lbb_match_name} -> {match_name_result[0]}")
            match["match_name"] = match_name_result[0]
            
            # 替换队伍名
            for team_key in ["team_a", "team_b"]:
                lbb_team = match[team_key]
                cursor.execute('SELECT web_team FROM team_mapping WHERE lbb_team = ? AND game_name = ?', 
                             (lbb_team, game_name))
                result = cursor.fetchone()
                if result:
                    print(f"[名称替换] 队伍: {lbb_team} -> {result[0]}")
                    match[team_key] = result[0]
            
            result_data.append(match)
        else:
            print(f"[名称替换] 跳过未匹配比赛: {lbb_match_name}")

    conn.close()
    print(f"[名称替换] 完成处理: {len(result_data)}条数据")
    return result_data