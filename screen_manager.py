# screen_manager.py
import time
import numpy as np
import logging

class ScreenManager:
    def __init__(self, controller, ocr):
        self.controller = controller
        self.ocr = ocr

    def get_center_coordinates(self, box):
        """计算矩形框中心坐标"""
        x_coords = [point[0] for point in box]
        y_coords = [point[1] for point in box]
        return int(sum(x_coords) / len(x_coords)), int(sum(y_coords) / len(y_coords))

    def check_text_in_roi(self, img_np, roi, expected_text):
        """检查指定区域内的文本是否包含预期文本"""
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
            logging.error("检查文本时出错: %s", e)
            return False

    def click_roi(self, roi):
        """点击指定区域的中心点"""
        x, y, w, h = roi
        center_x = x + w // 2
        center_y = y + h // 2
        self.controller.post_click(center_x, center_y).wait()

    def crop_and_recognize(self, center_x, center_y):
        """截取并识别指定点附近的倒T形状区域文本"""
        self.controller.post_screencap().wait()
        image = self.controller.cached_image
        if image is None or image.size == 0:
            logging.error("Failed to capture screen.")
            return []
        
        img_np = np.array(image)
        
        # 定义倒T形状的两个区域，以 center_x, center_y 为基准
        # 上方区域 [255, y-65, 228, 100]
        upper_x = 255
        upper_y = max(0, center_y - 65)  # 防止越界
        upper_w = 228
        upper_h = 100
        if upper_y + upper_h > img_np.shape[0] or upper_x + upper_w > img_np.shape[1]:
            logging.warning("Upper region exceeds image bounds, adjusting.")
            upper_h = min(upper_h, img_np.shape[0] - upper_y)
            upper_w = min(upper_w, img_np.shape[1] - upper_x)
        upper_crop = img_np[upper_y:upper_y + upper_h, upper_x:upper_x + upper_w]

        # 下方区域 [5, y+35, 710, 185]
        lower_x = 5
        lower_y = center_y + 35
        lower_w = 710
        lower_h = 185
        if lower_y + lower_h > img_np.shape[0] or lower_x + lower_w > img_np.shape[1]:
            logging.warning("Lower region exceeds image bounds, adjusting.")
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
            logging.info("No text recognized in the specified T-shaped regions.")
        
        return text_data

    def process_predict_box(self, box):
        """点击'预测中'并截取内容"""
        center_x, center_y = self.get_center_coordinates(box)
        logging.info("Clicking '预测中' at (%d, %d)", center_x, center_y)
        self.controller.post_click(center_x, center_y).wait()
        time.sleep(0.3)
        text_data = self.crop_and_recognize(center_x, center_y)
        time.sleep(0.3)
        self.controller.post_click(center_x, center_y).wait()
        return text_data

    def swipe_screen(self, distance=180):
        """滑动屏幕，向下滑动指定像素"""
        self.controller.post_swipe(360, 500, 360, 500 - distance, 500).wait()
        time.sleep(2)

    def count_predict_in_area(self, img_np, roi_coords):
        """统计指定区域内'预测中'的数量"""
        x, y, w, h = roi_coords
        roi = img_np[y:y+h, x:x+w]
        result = self.ocr.ocr(roi, cls=False)
        if not result or not result[0]:
            return 0
        return sum(1 for item in result[0] if item and len(item) > 1 and len(item[1]) > 0 and "预测中" in str(item[1][0]))

    def change_event_and_refresh(self, event_name="Dota2"):
        """切换项目并刷新"""
        event_coords = {"Dota2": (80, 135), "CS2": (190, 135), "LOL": (325, 135), "Valorant": (485, 135)}
        x, y = event_coords[event_name]
        self.controller.post_click(x, y).wait()
        time.sleep(5)
        self.controller.post_click(630, 1070).wait()
        time.sleep(5)
        logging.info("Switched to event '%s' and refreshed", event_name)
        return event_name
    
    def is_screen_static(self, img1, img2, threshold=0.95):
        """检查两张截图是否几乎相同（界面无变化）"""
        if img1.shape != img2.shape:
            return False
        diff = np.mean((img1 - img2) ** 2)
        similarity = 1 - diff / (255 ** 2)
        return similarity > threshold

    def scroll_to_bottom(self, refresh_roi):
        """点击刷新并向下滑动直到界面无变化"""
        self.controller.post_click(630, 1090).wait()  # 使用固定坐标点击刷新
        time.sleep(3)

        while True:
            self.controller.post_screencap().wait()
            img1 = np.array(self.controller.cached_image)
            self.swipe_screen(200)
            self.controller.post_screencap().wait()
            img2 = np.array(self.controller.cached_image)
            
            if self.is_screen_static(img1, img2):
                logging.info("Screen content stabilized, stopping scroll.")
                break
        time.sleep(2)

    def fetch_lbb_data(self, data_mgr, event_name):
        """
        使用while循环检查初始区域是否有'预测中'，有则点击并处理，滑动后继续检查，直到没有。
        然后从上到下处理四个区域，中下区域有特殊滑动处理。
        """
        # 定义区域
        upper_region = [308, 548, 100, 46]         
        middle_upper_region = [297, 723, 121, 46]    
        middle_lower_region = [302, 902, 117, 46]    
        lower_region = [307, 1080, 109, 48]        
        initial_check_region = [304, 402, 113, 46]   
        refresh_popup_roi = [603, 1047, 45, 47]     # "刷新"弹窗区域，用于排除

        lbb_matches = []  # 存储提取的比赛数据

        self.change_event_and_refresh(event_name)

        # 使用while循环检查初始区域是否有“预测中”
        while True:
            self.controller.post_screencap().wait()
            image = self.controller.cached_image
            if image is None or image.size == 0:
                logging.error("Failed to capture initial screen.")
                break
            img_np = np.array(image)
            initial_result = self.ocr.ocr(img_np[initial_check_region[1]:initial_check_region[1]+initial_check_region[3], 
                                        initial_check_region[0]:initial_check_region[0]+initial_check_region[2]], cls=False)

            # 检查是否有“预测中”
            if not (initial_result and initial_result[0] and any("预测中" in str(item[1][0]) for item in initial_result[0] if len(item) > 1 and len(item[1]) > 0)):
                logging.info("No '预测中' found in initial region, exiting initial loop.")
                break

            logging.info("Found '预测中' in initial region, processing.")
            # 找到并点击初始区域的“预测中”
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

            # 向下滑动180像素，继续检查
            self.swipe_screen(180)

        self.change_event_and_refresh(event_name)

        # 开始处理四个区域
        regions = [
            ("upper", upper_region),
            ("middle_upper", middle_upper_region),
            ("middle_lower", middle_lower_region),
            ("lower", lower_region)
        ]

        for region_name, region_coords in regions:
            self.controller.post_screencap().wait()
            image = self.controller.cached_image
            if image is None or image.size == 0:
                logging.error("Failed to capture screen for %s region.", region_name)
                continue
            img_np = np.array(image)
            result = self.ocr.ocr(img_np[region_coords[1]:region_coords[1]+region_coords[3], 
                                        region_coords[0]:region_coords[0]+region_coords[2]], cls=False)
            if not result or not result[0]:
                logging.info("No OCR result in %s region.", region_name)
                continue

            predict_boxes = [item[0] for item in result[0] if len(item) > 1 and len(item[1]) > 0 and "预测中" in str(item[1][0])]
            logging.info("Found %d '预测中' in %s region", len(predict_boxes), region_name)

            if region_name == "middle_lower" and predict_boxes:  
                self.controller.post_swipe(360, 500, 360, 635, 500).wait()
                time.sleep(1.5)
                self.controller.post_screencap().wait()
                image = self.controller.cached_image
                if image is None or image.size == 0:
                    logging.error("Failed to capture screen after swipe in middle_upper region.")
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

            # 每个区域处理完后刷新并滑动到底部
            self.controller.post_click(630, 1090).wait()
            time.sleep(5)
            while True:
                self.controller.post_screencap().wait()
                img1 = np.array(self.controller.cached_image)
                self.swipe_screen(367)
                self.controller.post_screencap().wait()
                img2 = np.array(self.controller.cached_image)
                if self.is_screen_static(img1, img2):
                    logging.info("Screen content stabilized in %s region, moving to next.", region_name)
                    break

        return lbb_matches