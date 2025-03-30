# kelly_calculator.py
'''从数据库中读取比赛赔率数据，计算 Kelly 分数和COINS值,依赖库：
sqlite3：用于操作 SQLite 数据库
os：用于文件路径操作
logging：用于记录错误日志, class KellyCalculator:
    def __init__(self, config):

        作用：计算 Kelly 分数，用于决定投注比例。
输入：
来自sql库的文件 由上文可知,有fetch的odds为赔率,littleblackbox_odds为赔率减一,即为净赔率
计算过程：
凯利公式{\displaystyle f^{*}={\frac {bp-q}{b}}={\frac {p(b+1)-1}{b}},}计算kelly_fraction,限制输出范围：返回 0 到 0.5（50%）之间的值,又有如果 kelly <= 0.02，返回 0（低于阈值不计算）。
计算 COINS = (kelly - 0.02) * 200。
四舍五入到最近的百位：round(COINS / 100) * 100'''

import os
import sqlite3
import logging
import glob
from datetime import datetime
import math

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("kelly_calculator.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("KellyCalculator")

class KellyCalculator:
    def __init__(self, config):
        """
        初始化 Kelly 计算器
        
        参数:
        config: 配置信息，包含数据目录等配置
        """
        self.config = config
        self.data_dir = config['fetch']['data_dir']
        logger.info(f"初始化Kelly计算器，数据目录: {self.data_dir}")
    
    def calculate_kelly(self, odds, probability):
        """
        计算凯利值
        
        参数:
        odds: 赔率，例如2.5
        probability: 获胜概率，范围0-1
        
        返回:
        凯利分数 (0 到 0.5 之间)
        """
        # 检查参数
        if odds <= 1 or probability <= 0 or probability >= 1:
            return 0
        
        # 计算净赔率 (b)
        b = odds - 1
        
        # 计算赢的概率 (p)
        p = probability
        
        # 计算输的概率 (q)
        q = 1 - p
        
        # 计算凯利公式: f* = (bp - q) / b 或 (p(b+1) - 1) / b
        kelly = (b * p - q) / b
        
        # 限制范围: 0-0.5之间
        kelly = max(0, min(0.5, kelly))
        
        # 低于阈值不计算
        if kelly <= 0.02:
            return 0
            
        return kelly
    
    def calculate_coins(self, kelly):
        """
        计算COINS值
        
        参数:
        kelly: 凯利分数
        
        返回:
        COINS值，四舍五入到最近的百位
        """
        if kelly <= 0.02:
            return 0
            
        # 计算COINS = (kelly - 0.02) * 200
        coins = (kelly - 0.02) * 200
        
        # 四舍五入到最近的百位
        coins = round(coins / 100) * 100
        
        return int(coins)
    
    def estimate_win_probability(self, web_odds, lbb_odds):
        """
        估计获胜概率
        
        参数:
        web_odds: 网站赔率
        lbb_odds: 小黑盒赔率
        
        返回:
        估计的获胜概率
        """
        # 基于赔率反推获胜概率: p = 1/odds
        web_prob = 1 / web_odds if web_odds > 1 else 0.5
        lbb_prob = 1 / lbb_odds if lbb_odds > 1 else 0.5
        
        # 综合两个来源的概率，这里可以使用加权平均
        # 假设网站赔率准确度更高，给予更高权重
        win_prob = 0.7 * web_prob + 0.3 * lbb_prob
        
        return win_prob
    
    def get_match_data(self, game_name):
        """
        从数据库获取比赛数据
        
        参数:
        game_name: 游戏名称，如CS2
        
        返回:
        比赛数据列表
        """
        game_folder = os.path.join(self.data_dir, game_name)
        if not os.path.exists(game_folder):
            logger.error(f"游戏目录不存在: {game_folder}")
            return []
        
        # 搜索所有的比赛文件夹
        match_dirs = [d for d in os.listdir(game_folder) if os.path.isdir(os.path.join(game_folder, d)) and not d.startswith('.')]
        logger.info(f"找到 {len(match_dirs)} 个比赛目录")
        
        all_match_data = []
        
        for match_dir in match_dirs:
            match_path = os.path.join(game_folder, match_dir)
            web_db_path = os.path.join(match_path, "web_matches.db")
            lbb_db_path = os.path.join(match_path, "lbb_matches.db")
            
            # 检查必要的数据库是否存在
            if not os.path.exists(web_db_path) and not os.path.exists(lbb_db_path):
                # 尝试查找旧版文件
                old_db_path = os.path.join(match_path, "matches.db")
                if os.path.exists(old_db_path) and os.path.exists(lbb_db_path):
                    web_db_path = old_db_path
                    logger.info(f"使用旧版数据库: {old_db_path}")
                else:
                    logger.warning(f"跳过 {match_dir}，缺少必要的数据库文件")
                    continue
            
            # 从web_matches.db读取数据
            web_matches = []
            if os.path.exists(web_db_path):
                conn = sqlite3.connect(web_db_path)
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        SELECT match_id, match_name, match_time, team_a, team_b, odds_a, odds_b
                        FROM matches
                    """)
                    for row in cursor.fetchall():
                        match_id, match_name, match_time, team_a, team_b, odds_a, odds_b = row
                        web_matches.append({
                            "match_id": match_id,
                            "match_name": match_name,
                            "match_time": match_time,
                            "team_a": team_a,
                            "team_b": team_b,
                            "odds_a": odds_a,
                            "odds_b": odds_b
                        })
                except Exception as e:
                    logger.error(f"读取 {web_db_path} 失败: {e}")
                finally:
                    conn.close()
            
            # 从lbb_matches.db读取数据
            lbb_matches = []
            if os.path.exists(lbb_db_path):
                conn = sqlite3.connect(lbb_db_path)
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        SELECT match_id, match_name, match_time, team_a, team_b, odds_a, odds_b
                        FROM matches
                    """)
                    for row in cursor.fetchall():
                        match_id, match_name, match_time, team_a, team_b, odds_a, odds_b = row
                        lbb_matches.append({
                            "match_id": match_id,
                            "match_name": match_name,
                            "match_time": match_time,
                            "team_a": team_a,
                            "team_b": team_b,
                            "odds_a": odds_a,
                            "odds_b": odds_b
                        })
                except Exception as e:
                    logger.error(f"读取 {lbb_db_path} 失败: {e}")
                finally:
                    conn.close()
            
            # 匹配web和lbb数据
            matched_pairs = []
            for web_match in web_matches:
                web_date = web_match["match_time"].split()[0]  # 只比较日期部分
                web_teams = {web_match["team_a"].lower(), web_match["team_b"].lower()}
                
                for lbb_match in lbb_matches:
                    lbb_date = lbb_match["match_time"].split()[0]  # 只比较日期部分
                    lbb_teams = {lbb_match["team_a"].lower(), lbb_match["team_b"].lower()}
                    
                    # 如果日期相同且队伍匹配（不考虑顺序）
                    if web_date == lbb_date and web_teams == lbb_teams:
                        matched_pairs.append({
                            "web_match": web_match,
                            "lbb_match": lbb_match,
                            "match_dir": match_path
                        })
                        break  # 找到匹配项后继续下一个web_match
            
            all_match_data.extend(matched_pairs)
        
        logger.info(f"成功配对 {len(all_match_data)} 场比赛")
        return all_match_data
    
    def save_kelly_data(self, game_name, match_data):
        """
        保存计算结果到数据库
        
        参数:
        game_name: 游戏名称
        match_data: 比赛数据（包含凯利值和COINS）
        
        返回:
        保存的记录数
        """
        game_folder = os.path.join(self.data_dir, game_name)
        kelly_db_path = os.path.join(game_folder, "kelly_results.db")
        
        try:
            conn = sqlite3.connect(kelly_db_path)
            cursor = conn.cursor()
            
            # 创建表（如果不存在）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kelly_results (
                    match_id TEXT PRIMARY KEY,
                    match_name TEXT,
                    match_time TEXT,
                    team_a TEXT,
                    team_b TEXT,
                    web_odds_a REAL,
                    web_odds_b REAL,
                    lbb_odds_a REAL,
                    lbb_odds_b REAL,
                    kelly_a REAL,
                    kelly_b REAL,
                    coins_a INTEGER,
                    coins_b INTEGER,
                    match_dir TEXT,
                    calculation_time TEXT
                )
            """)
            
            calculation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            count = 0
            
            for match in match_data:
                try:
                    web_match = match["web_match"]
                    lbb_match = match["lbb_match"]
                    match_dir = match["match_dir"]
                    
                    # 确定比赛和队伍信息
                    match_id = f"{game_name}_{web_match['team_a']}_{web_match['team_b']}_{web_match['match_time'].replace(' ', '_').replace(':', '')}"
                    match_name = web_match["match_name"]
                    match_time = web_match["match_time"]
                    team_a = web_match["team_a"]
                    team_b = web_match["team_b"]
                    
                    # 获取赔率
                    web_odds_a = web_match["odds_a"]
                    web_odds_b = web_match["odds_b"]
                    lbb_odds_a = lbb_match["odds_a"]
                    lbb_odds_b = lbb_match["odds_b"]
                    
                    # 计算凯利值，使用赔率估计概率
                    p_a_from_web = 1 / web_odds_a  # 从web赔率估计A队获胜概率
                    p_a_from_lbb = 1 / lbb_odds_a  # 从lbb赔率估计A队获胜概率
                    p_a = (p_a_from_web + p_a_from_lbb) / 2  # 简单平均，可以根据需要调整
                    
                    p_b_from_web = 1 / web_odds_b  # 从web赔率估计B队获胜概率
                    p_b_from_lbb = 1 / lbb_odds_b  # 从lbb赔率估计B队获胜概率
                    p_b = (p_b_from_web + p_b_from_lbb) / 2  # 简单平均
                    
                    # 标准化概率（确保总和为1）
                    sum_p = p_a + p_b
                    if sum_p > 0:
                        p_a = p_a / sum_p
                        p_b = p_b / sum_p
                    
                    # 使用两个来源的赔率平均值计算凯利值
                    kelly_a = self.calculate_kelly(web_odds_a, p_a)  # 对A队使用web赔率计算
                    kelly_b = self.calculate_kelly(web_odds_b, p_b)  # 对B队使用web赔率计算
                    
                    coins_a = self.calculate_coins(kelly_a)
                    coins_b = self.calculate_coins(kelly_b)
                    
                    # 保存结果
                    cursor.execute("""
                        INSERT OR REPLACE INTO kelly_results 
                        (match_id, match_name, match_time, team_a, team_b, 
                         web_odds_a, web_odds_b, lbb_odds_a, lbb_odds_b,
                         kelly_a, kelly_b, coins_a, coins_b, match_dir, calculation_time) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        match_id, match_name, match_time,
                        team_a, team_b, 
                        web_odds_a, web_odds_b,
                        lbb_odds_a, lbb_odds_b,
                        kelly_a, kelly_b,
                        coins_a, coins_b,
                        match_dir, calculation_time
                    ))
                    count += 1
                except Exception as e:
                    logger.error(f"保存比赛 {match['match_id']} 结果时出错: {str(e)}")
            
            conn.commit()
            conn.close()
            
            logger.info(f"已保存 {count} 条凯利计算结果到 {kelly_db_path}")
            return count
            
        except Exception as e:
            logger.error(f"保存凯利计算结果时出错: {str(e)}")
            return 0
    
    def process_game(self, game_name):
        """
        处理指定游戏的所有比赛数据
        
        参数:
        game_name: 游戏名称
        
        返回:
        处理的比赛数和保存的结果数
        """
        logger.info(f"开始处理游戏 {game_name} 的比赛数据")
        
        # 获取比赛数据
        match_data = self.get_match_data(game_name)
        if not match_data:
            logger.warning(f"未找到游戏 {game_name} 的有效比赛数据")
            return 0, 0
        
        logger.info(f"找到 {len(match_data)} 场比赛数据")
        
        # 打印凯利分数和COINS结果
        for match in match_data:
            if match["coins_a"] > 0 or match["coins_b"] > 0:
                logger.info(f"比赛: {match['match_name']} - {match['team_a']} vs {match['team_b']}")
                if match["coins_a"] > 0:
                    logger.info(f"  {match['team_a']}: Kelly={match['kelly_a']:.4f}, COINS={match['coins_a']}")
                if match["coins_b"] > 0:
                    logger.info(f"  {match['team_b']}: Kelly={match['kelly_b']:.4f}, COINS={match['coins_b']}")
        
        # 保存结果
        saved_count = self.save_kelly_data(game_name, match_data)
        
        return len(match_data), saved_count

def main():
    """
    主函数，从所有游戏和比赛数据中计算凯利值
    """
    try:
        # 简单配置
        config = {
            'fetch': {
                'data_dir': os.path.join(os.path.dirname(__file__), 'data')
            }
        }
        
        calculator = KellyCalculator(config)
        
        # 获取所有游戏目录
        data_dir = config['fetch']['data_dir']
        if not os.path.exists(data_dir):
            logger.error(f"数据目录不存在: {data_dir}")
            return
        
        game_folders = [d for d in os.listdir(data_dir) 
                      if os.path.isdir(os.path.join(data_dir, d)) 
                      and not d.startswith('.')]
        
        total_matches = 0
        total_saved = 0
        
        for game in game_folders:
            matches, saved = calculator.process_game(game)
            total_matches += matches
            total_saved += saved
        
        logger.info(f"处理完成，共处理 {total_matches} 场比赛，保存 {total_saved} 条结果")
        
    except Exception as e:
        logger.error(f"计算凯利值时出错: {str(e)}")

if __name__ == "__main__":
    main()
