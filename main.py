# main.py - 主程序，协调整个系统的运行流程
import traceback
import numpy as np
import os
import time
from init_manager import InitManager
from screen_manager import ScreenManager
from data_manager import DataManager
from fetch_odds import fetch_team_odds
from team_match import match_teams_and_names, replace_team_and_match_name

def main():
    """
    主函数，协调整个系统的运行：
    1. 加载配置并初始化系统
    2. 导航到小黑盒的赛事中心
    3. 顺序处理每个游戏项目的数据
    4. 整合网络数据和小黑盒数据
    5. 保存最终结果到数据库
    """
    # 加载配置文件
    with open('config.yaml', 'r', encoding='utf-8') as f:
        import yaml
        config = yaml.safe_load(f)
    print("[主程序] 已加载配置文件")

    # 获取需要跳过的游戏列表
    skip_games = config.get('skip_games', [])
    if skip_games:
        print(f"[主程序] 将跳过以下游戏: {skip_games}")
    
    # 初始化系统组件
    print("[主程序] 开始系统初始化...")
    init = InitManager()
    controller, ocr = init.initialize_all()
    screen_mgr = ScreenManager(controller, ocr)
    data_mgr = DataManager(init.config)
    print("[主程序] 系统初始化完成")

    # 导航到正确位置（赛事中心）
    print("[主程序] 等待5秒后开始导航到赛事中心...")
    time.sleep(5)
    checks = [
        {"roi": [597, 1052, 59, 37], "text": "刷新"},
        {"roi": [462, 1180, 82, 88], "text": "游戏库"},
        {"roi": [370, 270, 105, 45], "text": "赛事中心"}
    ]
    for attempt in range(3):
        print(f"[主程序] 导航尝试 {attempt+1}/3")
        controller.post_screencap().wait()
        image = controller.cached_image
        if image is None or image.size == 0:
            print("[主程序] 截图失败")
            break
        img_np = np.array(image)
        
        # 检查是否已在刷新页面
        if screen_mgr.check_text_in_roi(img_np, checks[0]["roi"], "刷新"):
            print("[主程序] 已在刷新页面，点击刷新并选择CS2")
            screen_mgr.refresh()
            time.sleep(10)
            screen_mgr.controller.post_click(80, 135).wait()  # 选择默认游戏
            time.sleep(5)
            break
            
        # 检查并导航到赛事中心
        if screen_mgr.check_text_in_roi(img_np, checks[2]["roi"], "赛事中心"):
            print("[主程序] 发现赛事中心按钮，点击进入")
            screen_mgr.click_roi(checks[2]["roi"])
            time.sleep(3)
            continue
            
        # 检查并导航到游戏库
        if screen_mgr.check_text_in_roi(img_np, checks[1]["roi"], "游戏库"):
            print("[主程序] 发现游戏库按钮，点击进入")
            screen_mgr.click_roi(checks[1]["roi"])
            time.sleep(3)
            continue
            
        # 如果都没找到，重新初始化
        print("[主程序] 未找到导航元素，重新初始化")
        # 第三次尝试前，延长等待时间
        if attempt == 2:
            print("[主程序] 第三次尝试前延长等待时间到15秒")
            time.sleep(15)
        else:
            time.sleep(3)
        init.initialize_all()

    # 顺序处理每个游戏项目
    event_list = list(config['urls']['games'].keys())
    print(f"[主程序] 开始处理 {len(event_list)} 个游戏项目: {event_list}")
    
    for event_name in event_list:
        # 检查是否跳过当前游戏
        if event_name in skip_games:
            print(f"[主程序] 跳过 {event_name}（配置中指定）")
            continue
            
        print(f"\n[主程序] ===== 开始处理游戏: {event_name} =====")
        try:
            # 1. 获取网络数据（不依赖结果执行后续逻辑）
            print(f"[主程序] 获取 {event_name} 网络数据")
            status, web_data = fetch_team_odds(
                config, 
                {event_name: config['urls']['games'][event_name]}
            )
            if status != 0 or not web_data:
                print(f"[主程序] [{event_name}] 网络数据获取失败或为空，使用本地数据继续")

            # 2. 获取小黑盒界面数据（60秒超时）
            print(f"[主程序] 获取 {event_name} 小黑盒界面数据（最多60秒）")
            start_time = time.time()
            lbb_data = None
            while time.time() - start_time < 60:
                lbb_data = screen_mgr.fetch_lbb_data(data_mgr, event_name)
                if lbb_data:
                    print(f"[主程序] 成功获取 {len(lbb_data)} 条小黑盒数据")
                    break
                time.sleep(1)
                
            if not lbb_data:
                print(f"[主程序] [{event_name}] 60秒内未能获取小黑盒数据，跳过处理")
                continue

            # 3. 匹配队伍和比赛名称，并替换标准化名称
            match_folder = os.path.join(config['fetch']['data_dir'], event_name)
            print(f"[主程序] 处理游戏: {event_name}, 路径: {match_folder}")
            os.makedirs(match_folder, exist_ok=True)  # 确保目录存在
            
            # 3.1 匹配队伍和比赛名称
            print(f"[主程序] 匹配 {event_name} 的队伍和比赛名称")
            match_teams_and_names(web_data, lbb_data, event_name, match_folder)
            
            # 3.2 替换标准化名称
            print(f"[主程序] 替换 {event_name} 的标准化名称")
            lbb_data = replace_team_and_match_name(lbb_data, event_name, match_folder)
            
            # 4. 保存处理后的数据到数据库
            print(f"[主程序] 保存 {event_name} 的 {len(lbb_data)} 条处理后数据")
            for match in lbb_data:
                if "match_id" in match:
                    match_id = match["match_id"]
                    data_mgr.save_to_sqlite(event_name, match["match_name"], match, match_id=match_id)
                else:
                    data_mgr.save_to_sqlite(event_name, match["match_name"], match)
            
            print(f"[主程序] 完成 {event_name} 的数据处理")

        except Exception as e:
            print(f"[主程序] [{event_name}] 处理过程中发生错误: {str(e)}")
            print(traceback.format_exc())
            continue
    
    print("[主程序] 所有游戏项目处理完成")

if __name__ == "__main__":
    main()