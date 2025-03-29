# screen_manager.py
import time
import numpy as np
import logging

class ScreenManager:
    """
    屏幕管理器：负责与模拟器界面交互，包括截图、识别、点击和滑动操作，
    以及提取比赛数据
    """
    def __init__(self, controller, ocr):
        """初始化屏幕管理器"""
        self.controller = controller
        self.ocr = ocr
        print("[屏幕] 初始化屏幕管理器")

    def get_center_coordinates(self, box):
        """计算矩形框中心坐标，用于精确点击"""
        x_coords = [point[0] for point in box]
        y_coords = [point[1] for point in box]
        return int(sum(x_coords) / len(x_coords)), int(sum(y_coords) / len(y_coords))

    def check_text_in_roi(self, img_np, roi, expected_text):
        """检查指定区域(ROI)内的文本是否包含预期文本"""
        try:
            x, y, w, h = roi
            if x + w > img_np.shape[1] or y + h > img_np.shape[0]:
                return False
            cropped_img = img_np[y:y+h, x:x+w]
            result = self.ocr.ocr(cropped_img, cls=False)
            if not result or not result[0]:
                return False
            detected_texts = [item[1][0] for line in result for item in line if len(item) > 1 and len(item[1]) > 0]
            return expected_text in "\n".join(detected_texts)
        except Exception as e:
            print(f"[屏幕] 检查文本时出错: {e}")
            return False

    def click_roi(self, roi):
        """点击指定区域的中心点"""
        x, y, w, h = roi
        center_x = x + w // 2
        center_y = y + h // 2
        print(f"[屏幕] 点击区域: ({x},{y},{w},{h}) 中心点: ({center_x}, {center_y})")
        self.controller.post_click(center_x, center_y).wait()

    def crop_and_recognize(self, center_x, center_y):
        """截取并识别指定点附近的倒T形状区域文本"""
        self.controller.post_screencap().wait()
        image = self.controller.cached_image
        if image is None or image.size == 0:
            print("[屏幕] 截图失败")
            return []
        
        img_np = np.array(image)
        print(f"[屏幕] 识别中心点 ({center_x}, {center_y}) 周围的倒T形区域")
        
        # 定义倒T形状的两个区域，以 center_x, center_y 为基准
        # 上方区域 [255, y-65, 228, 100]
        upper_x = 255
        upper_y = max(0, center_y - 65)  # 防止越界
        upper_w = 228
        upper_h = 100
        if upper_y + upper_h > img_np.shape[0] or upper_x + upper_w > img_np.shape[1]:
            print("[屏幕] 上方区域超出图像边界，正在调整")
            upper_h = min(upper_h, img_np.shape[0] - upper_y)
            upper_w = min(upper_w, img_np.shape[1] - upper_x)
        upper_crop = img_np[upper_y:upper_y + upper_h, upper_x:upper_x + upper_w]

        # 下方区域 [5, y+35, 710, 185]
        lower_x = 5
        lower_y = center_y + 35
        lower_w = 710
        lower_h = 185
        if lower_y + lower_h > img_np.shape[0] or lower_x + lower_w > img_np.shape[1]:
            print("[屏幕] 下方区域超出图像边界，正在调整")
            lower_h = min(lower_h, img_np.shape[0] - lower_y)
            lower_w = min(lower_w, img_np.shape[1] - lower_x)
        lower_crop = img_np[lower_y:lower_y + lower_h, lower_x:lower_x + lower_w]

        # 对两个区域分别进行 OCR 识别
        upper_result = self.ocr.ocr(upper_crop, cls=False)
        lower_result = self.ocr.ocr(lower_crop, cls=False)

        # 初始化返回结果
        text_data = []

        # 处理上方区域的结果
        if upper_result and upper_result[0]:
            for item in upper_result[0]:
                if item and len(item) > 1 and len(item[1]) > 0:
                    coords = self.get_center_coordinates(item[0])
                    adjusted_coords = [coords[0] + upper_x, coords[1] + upper_y]
                    text_data.append({
                        "text": str(item[1][0]).strip(),
                        "coordinates": adjusted_coords
                    })

        # 处理下方区域的结果
        if lower_result and lower_result[0]:
            for item in lower_result[0]:
                if item and len(item) > 1 and len(item[1]) > 0:
                    coords = self.get_center_coordinates(item[0])
                    adjusted_coords = [coords[0] + lower_x, coords[1] + lower_y]
                    text_data.append({
                        "text": str(item[1][0]).strip(),
                        "coordinates": adjusted_coords
                    })

        if not text_data:
            print("[屏幕] 在指定的T形区域中未识别到文本")
        else:
            print(f"[屏幕] 识别到 {len(text_data)} 个文本项")
        
        return text_data

    def process_predict_box(self, box):
        """点击'预测中'按钮并截取内容"""
        center_x, center_y = self.get_center_coordinates(box)
        print(f"[屏幕] 点击'预测中'按钮，坐标: ({center_x}, {center_y})")
        self.controller.post_click(center_x, center_y).wait()
        time.sleep(0.3)
        text_data = self.crop_and_recognize(center_x, center_y)
        time.sleep(0.3)
        self.controller.post_click(center_x, center_y).wait()  # 点击关闭弹窗
        return text_data

    def swipe_screen(self, distance=180):
        """滑动屏幕，向下滑动指定像素"""
        print(f"[屏幕] 向下滑动 {distance} 像素")
        self.controller.post_swipe(360, 500, 360, 500 - distance, 500).wait()
        time.sleep(2)

    def count_predict_in_area(self, img_np, roi_coords):
        """统计指定区域内'预测中'的数量"""
        x, y, w, h = roi_coords
        roi = img_np[y:y+h, x:x+w]
        result = self.ocr.ocr(roi, cls=False)
        if not result or not result[0]:
            return 0
        predict_count = sum(1 for item in result[0] if item and len(item) > 1 and len(item[1]) > 0 and "预测中" in str(item[1][0]))
        print(f"[屏幕] 区域 ({x},{y},{w},{h}) 发现 {predict_count} 个'预测中'")
        return predict_count

    def refresh(self):
        """
        点击刷新按钮并等待页面加载完成
        返回: bool - 页面是否成功加载
        """
        print("[屏幕] 点击刷新按钮")
        # 刷新按钮坐标
        refresh_x, refresh_y = 630, 1070
        self.controller.post_click(refresh_x, refresh_y).wait()
        time.sleep(3)  # 等待基本加载
        
        # 检查刷新按钮周围区域是否加载完成
        max_attempts = 10
        for attempt in range(max_attempts):
            self.controller.post_screencap().wait()
            image = self.controller.cached_image
            if image is None or image.size == 0:
                print(f"[屏幕] 截图失败，尝试 {attempt + 1}/{max_attempts}")
                time.sleep(3)
                continue
                
            # 检查刷新按钮周围区域
            img_np = np.array(image)
            # 定义刷新按钮周围100x100像素的区域
            refresh_region = [refresh_x - 50, refresh_y - 50, 100, 100]
            # 确保区域不超出图像边界
            refresh_region[0] = max(0, refresh_region[0])
            refresh_region[1] = max(0, refresh_region[1])
            if refresh_region[0] + refresh_region[2] > img_np.shape[1]:
                refresh_region[2] = img_np.shape[1] - refresh_region[0]
            if refresh_region[1] + refresh_region[3] > img_np.shape[0]:
                refresh_region[3] = img_np.shape[0] - refresh_region[1]
                
            refresh_roi = img_np[refresh_region[1]:refresh_region[1]+refresh_region[3], 
                               refresh_region[0]:refresh_region[0]+refresh_region[2]]
            
            result = self.ocr.ocr(refresh_roi, cls=False)
            if result and result[0]:
                texts = [item[1][0] for item in result[0] if len(item) > 1 and len(item[1]) > 0]
                if any("刷新" in text for text in texts):
                    print("[屏幕] 页面加载完成，发现刷新按钮")
                    return True
            
            print(f"[屏幕] 等待页面加载，尝试 {attempt + 1}/{max_attempts}")
            time.sleep(3)
        
        print("[屏幕] 页面加载超时")
        return False

    def change_event_and_refresh(self, event_name="Dota2"):
        """切换游戏项目并刷新页面"""
        event_coords = {"Dota2": (80, 135), "CS2": (190, 135), "LOL": (325, 135), "Valorant": (485, 135)}
        x, y = event_coords[event_name]
        print(f"[屏幕] 切换到游戏项目: {event_name}，坐标: ({x}, {y})")
        self.controller.post_click(x, y).wait()
        time.sleep(3)
        return self.refresh()
    
    def is_screen_static(self, img1, img2, threshold=0.95):
        """检查两张截图是否几乎相同（界面无变化）"""
        if img1.shape != img2.shape:
            return False
        diff = np.mean((img1 - img2) ** 2)
        similarity = 1 - diff / (255 ** 2)
        print(f"[屏幕] 屏幕相似度: {similarity:.4f}, 阈值: {threshold}")
        return similarity > threshold

    def scroll_to_bottom(self, refresh_roi):
        """点击刷新并向下滑动直到界面无变化"""
        print("[屏幕] 开始滑动到底部流程")
        self.refresh()
        time.sleep(3)

        while True:
            self.controller.post_screencap().wait()
            img1 = np.array(self.controller.cached_image)
            self.swipe_screen(200)
            self.controller.post_screencap().wait()
            img2 = np.array(self.controller.cached_image)
            
            if self.is_screen_static(img1, img2):
                print("[屏幕] 屏幕内容稳定，停止滑动")
                break
        time.sleep(2)

    def fetch_lbb_data(self, data_mgr, event_name):
        """
        从小黑盒界面获取比赛数据:
        1. 切换到指定游戏项目并刷新
        2. 检查并处理初始区域的"预测中"
        3. 依次处理各个区域的"预测中"
        4. 返回所有提取的比赛数据
        """
        # 定义区域
        upper_region = [308, 548, 100, 46]         
        middle_upper_region = [297, 723, 121, 46]    
        middle_lower_region = [302, 902, 117, 46]    
        lower_region = [307, 1080, 109, 48]        
        initial_check_region = [304, 402, 113, 46]   
        refresh_popup_roi = [603, 1047, 45, 47]     # "刷新"弹窗区域，用于排除

        lbb_matches = []  # 存储提取的比赛数据
        print(f"[屏幕] 开始获取 {event_name} 比赛数据")

        self.change_event_and_refresh(event_name)

        # 使用while循环检查初始区域是否有"预测中"
        while True:
            self.controller.post_screencap().wait()
            image = self.controller.cached_image
            if image is None or image.size == 0:
                print("[屏幕] 截取初始屏幕失败")
                break
            img_np = np.array(image)
            initial_result = self.ocr.ocr(img_np[initial_check_region[1]:initial_check_region[1]+initial_check_region[3], 
                                        initial_check_region[0]:initial_check_region[0]+initial_check_region[2]], cls=False)

            # 检查是否有"预测中"
            predicts_found = False
            if initial_result and initial_result[0]:
                predicts_found = any("预测中" in str(item[1][0]) for item in initial_result[0] if len(item) > 1 and len(item[1]) > 0)
            
            if not predicts_found:
                print("[屏幕] 初始区域未发现'预测中'，退出初始循环")
                break

            print("[屏幕] 在初始区域发现'预测中'，处理中")
            # 找到并点击初始区域的"预测中"
            predict_boxes = [item[0] for item in initial_result[0] if len(item) > 1 and len(item[1]) > 0 and "预测中" in str(item[1][0])]
            if predict_boxes:
                adjusted_box = [[x + initial_check_region[0], y + initial_check_region[1]] for x, y in predict_boxes[0]]
                text_data = self.process_predict_box(adjusted_box)  # 点击并截图特定区域
                match_name, processed_data = data_mgr.process_text_data(text_data)
                if match_name and processed_data:
                    lbb_matches.append({
                        "match_name": match_name,
                        "team_a": processed_data["team_a"],
                        "team_b": processed_data["team_b"],
                        "odds_a": str(processed_data["odds_a"]),
                        "odds_b": str(processed_data["odds_b"]),
                        "time": processed_data["time"]
                    })
                    print(f"[屏幕] 成功提取初始区域比赛: {match_name}")

            # 向下滑动180像素，继续检查
            self.swipe_screen(180)

        print(f"[屏幕] 初始区域处理完成，开始处理四个固定区域")
        self.change_event_and_refresh(event_name)

        # 开始处理四个区域
        regions = [
            ("upper", upper_region),
            ("middle_upper", middle_upper_region),
            ("middle_lower", middle_lower_region),
            ("lower", lower_region)
        ]

        for region_name, region_coords in regions:
            print(f"[屏幕] 处理 {region_name} 区域: {region_coords}")
            self.controller.post_screencap().wait()
            image = self.controller.cached_image
            if image is None or image.size == 0:
                print(f"[屏幕] 截取 {region_name} 区域屏幕失败")
                continue
            img_np = np.array(image)
            result = self.ocr.ocr(img_np[region_coords[1]:region_coords[1]+region_coords[3], 
                                        region_coords[0]:region_coords[0]+region_coords[2]], cls=False)
            if not result or not result[0]:
                print(f"[屏幕] {region_name} 区域无OCR结果")
                continue

            predict_boxes = [item[0] for item in result[0] if len(item) > 1 and len(item[1]) > 0 and "预测中" in str(item[1][0])]
            print(f"[屏幕] 在 {region_name} 区域发现 {len(predict_boxes)} 个'预测中'")

            if region_name == "middle_lower" and predict_boxes:  
                print("[屏幕] 中下区域特殊处理：向下滑动")
                self.controller.post_swipe(360, 500, 360, 635, 500).wait()
                time.sleep(1.5)
                self.controller.post_screencap().wait()
                image = self.controller.cached_image
                if image is None or image.size == 0:
                    print("[屏幕] 截取中下区域屏幕失败")
                    continue
                img_np = np.array(image)
                adjusted_y = region_coords[1] + 135
                result = self.ocr.ocr(img_np[adjusted_y:adjusted_y+region_coords[3], 
                                            region_coords[0]:region_coords[0]+region_coords[2]], cls=False)
                if result and result[0]:
                    predict_boxes = [item[0] for item in result[0] if len(item) > 1 and len(item[1]) > 0 and "预测中" in str(item[1][0])]
                    for box in predict_boxes:
                        adjusted_box = [[x + region_coords[0], y + adjusted_y] for x, y in box]
                        text_data = self.process_predict_box(adjusted_box)
                        match_name, processed_data = data_mgr.process_text_data(text_data)
                        if match_name and processed_data:
                            lbb_matches.append({
                                "match_name": match_name,
                                "team_a": processed_data["team_a"],
                                "team_b": processed_data["team_b"],
                                "odds_a": str(processed_data["odds_a"]),
                                "odds_b": str(processed_data["odds_b"]),
                                "time": processed_data["time"]
                            })
                            print(f"[屏幕] 成功提取中下区域比赛: {match_name}")

            else:
                # 其他区域的常规处理
                for box in predict_boxes:
                    adjusted_box = [[x + region_coords[0], y + region_coords[1]] for x, y in box]
                    text_data = self.process_predict_box(adjusted_box)
                    match_name, processed_data = data_mgr.process_text_data(text_data)
                    if match_name and processed_data:
                        lbb_matches.append({
                            "match_name": match_name,
                            "team_a": processed_data["team_a"],
                            "team_b": processed_data["team_b"],
                            "odds_a": str(processed_data["odds_a"]),
                            "odds_b": str(processed_data["odds_b"]),
                            "time": processed_data["time"]
                        })
                        print(f"[屏幕] 成功提取 {region_name} 区域比赛: {match_name}")

            # 每个区域处理完后刷新并滑动到底部
            self.refresh()
            time.sleep(5)
            while True:
                self.controller.post_screencap().wait()
                img1 = np.array(self.controller.cached_image)
                self.swipe_screen(367)
                self.controller.post_screencap().wait()
                img2 = np.array(self.controller.cached_image)
                if self.is_screen_static(img1, img2):
                    print(f"[屏幕] {region_name} 区域内容稳定，移动到下一个区域")
                    break

        return lbb_matches