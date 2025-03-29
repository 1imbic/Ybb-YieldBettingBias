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
    with open('config.yaml', 'r', encoding='utf-8') as f:
        import yaml
        config = yaml.safe_load(f)

    skip_games = config.get('skip_games', [])
    # 初始化
    init = InitManager()
    controller, ocr = init.initialize_all()
    screen_mgr = ScreenManager(controller, ocr)
    data_mgr = DataManager(init.config)

    # 导航到正确位置
    time.sleep(5)
    checks = [
        {"roi": [597, 1052, 59, 37], "text": "刷新"},
        {"roi": [462, 1180, 82, 88], "text": "游戏库"},
        {"roi": [370, 270, 105, 45], "text": "赛事中心"}
    ]
    for _ in range(3):
        controller.post_screencap().wait()
        image = controller.cached_image
        if image is None or image.size == 0:
            print("Failed to capture screen image.")
            break
        img_np = np.array(image)
        if screen_mgr.check_text_in_roi(img_np, checks[0]["roi"], "刷新"):
            screen_mgr.controller.post_click(630, 1090).wait()
            time.sleep(10)
            screen_mgr.controller.post_click(80, 135).wait()
            time.sleep(5)
            break
        if screen_mgr.check_text_in_roi(img_np, checks[2]["roi"], "赛事中心"):
            screen_mgr.click_roi(checks[2]["roi"])
            time.sleep(3)
            continue
        if screen_mgr.check_text_in_roi(img_np, checks[1]["roi"], "游戏库"):
            screen_mgr.click_roi(checks[1]["roi"])
            time.sleep(3)
            continue
        init.initialize_all()
        time.sleep(3)

    # 顺序处理每个事件
    event_list = list(config['urls']['games'].keys())
    for event_name in event_list:
        if event_name in skip_games:
            print(f"Skipping {event_name} as specified in config.")
            continue
        try:
            # 获取网络数据（不依赖结果执行后续逻辑）
            status, web_data = fetch_team_odds(
                config, 
                {event_name: config['urls']['games'][event_name]}
            )
            if status != 0 or not web_data:
                print(f"[{event_name}] Web data fetch failed or empty, proceeding with local data.")

            # 合并 fetch_lbb_data 调用，保留 60 秒超时
            start_time = time.time()
            lbb_data = None
            while time.time() - start_time < 60:
                lbb_data = screen_mgr.fetch_lbb_data(data_mgr, event_name)
                if lbb_data:
                    break
                time.sleep(1)
            if not lbb_data:
                print(f"[{event_name}] Failed to fetch lbb_data within 60 seconds, skipping.")
                continue

            # 确保 match_teams_and_names 和 replace_team_and_match_name 必定触发
            match_folder = os.path.join(config['fetch']['data_dir'], event_name)  # 统一路径为 data/CS2
            match_teams_and_names(web_data, lbb_data, event_name, match_folder)
            lbb_data = replace_team_and_match_name(lbb_data, event_name, match_folder)
            for match in lbb_data:
                if "match_id" in match:
                    match_id = match["match_id"]
                    data_mgr.save_to_sqlite(event_name, match["match_name"], match, match_id=match_id)

        except Exception as e:
            print(f"[{event_name}] 处理过程中发生错误: {str(e)}")
            print(traceback.format_exc())
            continue

if __name__ == "__main__":
    main()