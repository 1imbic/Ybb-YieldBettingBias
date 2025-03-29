import sqlite3
import os
from datetime import datetime, timedelta
import difflib

def initialize_db(match_folder):
    db_path = os.path.join(match_folder, 'mappings.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS team_mapping (
        lbb_team TEXT, web_team TEXT, game_name TEXT, last_updated TEXT, PRIMARY KEY (lbb_team, game_name))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS match_name_mapping (
        lbb_match_name TEXT, web_match_name TEXT, game_name TEXT, last_updated TEXT, PRIMARY KEY (lbb_match_name, game_name))''')
    conn.commit()
    return conn, cursor

def get_initials(team):
    return ''.join(word[0].upper() for word in team.split() if word)

def fuzzy_match(team1, team2, threshold=0.8):
    initials1, initials2 = get_initials(team1), get_initials(team2)
    if initials1 == initials2:
        return True
    similarity = difflib.SequenceMatcher(None, team1.lower(), team2.lower()).ratio()
    return similarity > threshold

def match_teams_and_names(web_data, lbb_data, game_name, match_folder):
    conn, cursor = initialize_db(match_folder)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 以时间最新的 lbb_match 为基准
    latest_lbb_match = max(lbb_data, key=lambda x: datetime.strptime(x["time"], '%Y-%m-%d %H:%M:%S'))
    lbb_match_name = latest_lbb_match["match_name"]

    # 检查是否已有匹配规则
    cursor.execute('SELECT web_match_name FROM match_name_mapping WHERE lbb_match_name = ? AND game_name = ?', 
                   (lbb_match_name, game_name))
    match_name_result = cursor.fetchone()
    if match_name_result:
        web_match_name = match_name_result[0]
        # 从 web_data 或 matches.db 中查找对应的 web_match
        web_match = None
        if web_data:
            for match in web_data:
                if match["MatchName"] == web_match_name:
                    web_match = match
                    break
        if not web_match:
            matches_db_path = os.path.join(match_folder, 'matches.db')
            try:
                matches_conn = sqlite3.connect(matches_db_path)
                matches_cursor = matches_conn.cursor()
                matches_cursor.execute('SELECT match_name, match_time, team_a, team_b FROM matches WHERE match_name = ?', (web_match_name,))
                result = matches_cursor.fetchone()
                matches_conn.close()
                if result:
                    web_match = {"MatchName": result[0], "MatchTime": result[1], "TeamA": result[2], "TeamB": result[3]}
            except sqlite3.Error:
                pass
    else:
        # 未找到匹配规则，重新匹配
        if web_data:
            web_match = min(web_data, key=lambda x: abs(datetime.strptime(x["MatchTime"], '%Y-%m-%d %H:%M:%S') - 
                                                        datetime.strptime(latest_lbb_match["time"], '%Y-%m-%d %H:%M:%S')))
            web_match_name = web_match["MatchName"]
        else:
            # web_data 为空，从 matches.db 读取最新数据
            matches_db_path = os.path.join(match_folder, 'matches.db')
            try:
                matches_conn = sqlite3.connect(matches_db_path)
                matches_cursor = matches_conn.cursor()
                matches_cursor.execute('SELECT match_name, match_time, team_a, team_b FROM matches ORDER BY match_time DESC LIMIT 1')
                result = matches_cursor.fetchone()
                matches_conn.close()
                if result:
                    web_match_name, web_time_str, team_a, team_b = result
                    web_match = {
                        "MatchName": web_match_name,
                        "MatchTime": web_time_str,
                        "TeamA": team_a,
                        "TeamB": team_b
                    }
                else:
                    web_match_name = lbb_match_name
                    web_match = {
                        "MatchName": web_match_name,
                        "MatchTime": latest_lbb_match["time"],
                        "TeamA": None,
                        "TeamB": None
                    }
            except sqlite3.Error:
                web_match_name = lbb_match_name
                web_match = {
                    "MatchName": web_match_name,
                    "MatchTime": latest_lbb_match["time"],
                    "TeamA": None,
                    "TeamB": None
                }
        
        # 存储新匹配规则
        cursor.execute('INSERT OR REPLACE INTO match_name_mapping (lbb_match_name, web_match_name, game_name, last_updated) VALUES (?, ?, ?, ?)',
                       (lbb_match_name, web_match_name, game_name, now))

    # 队伍匹配
    for lbb_match in lbb_data:
        if lbb_match["match_name"] == lbb_match_name:
            lbb_time = datetime.strptime(lbb_match["time"], '%Y-%m-%d %H:%M:%S')
            web_time = datetime.strptime(web_match["MatchTime"], '%Y-%m-%d %H:%M:%S')
            if abs(web_time - lbb_time) <= timedelta(hours=0.5):
                web_teams = [web_match["TeamA"], web_match["TeamB"]]
                lbb_teams = [lbb_match["team_a"], lbb_match["team_b"]]
                for i, lbb_team in enumerate(lbb_teams):
                    cursor.execute('SELECT web_team FROM team_mapping WHERE lbb_team = ? AND game_name = ?', 
                                   (lbb_team, game_name))
                    team_result = cursor.fetchone()
                    if not team_result and web_teams[0] and web_teams[1]:
                        # 按顺序匹配队伍
                        web_team = web_teams[i] if i < len(web_teams) else None
                        if web_team and fuzzy_match(lbb_team, web_team):
                            cursor.execute('INSERT OR REPLACE INTO team_mapping (lbb_team, web_team, game_name, last_updated) VALUES (?, ?, ?, ?)',
                                           (lbb_team, web_team, game_name, now))

    conn.commit()
    conn.close()

def replace_team_and_match_name(lbb_data, game_name, match_folder):
    conn, cursor = initialize_db(match_folder)
    
    for match in lbb_data:
        # 替换队伍名
        for team_key in ["team_a", "team_b"]:
            lbb_team = match[team_key]
            cursor.execute('SELECT web_team FROM team_mapping WHERE lbb_team = ? AND game_name = ?', (lbb_team, game_name))
            result = cursor.fetchone()
            if result:
                match[team_key] = result[0]

        # 替换比赛名
        lbb_match_name = match["match_name"]
        cursor.execute('SELECT web_match_name FROM match_name_mapping WHERE lbb_match_name = ? AND game_name = ?', (lbb_match_name, game_name))
        match_name_result = cursor.fetchone()
        if match_name_result:
            match["match_name"] = match_name_result[0]

    conn.close()
    return lbb_data