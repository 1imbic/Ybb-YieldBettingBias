# init_manager.py
import os
import yaml
import subprocess
import time
import logging
from paddleocr import PaddleOCR
from maa.toolkit import Toolkit
from maa.controller import AdbController
from maa.define import MaaAdbScreencapMethodEnum, MaaAdbInputMethodEnum

class InitManager:
    def __init__(self, config_path='config.yaml'):
        self.config = self.load_config(config_path)

    def load_config(self, config_path):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logging.info("Loaded config: %s", config)
                return config
        except Exception as e:
            logging.error("Failed to load %s: %s", config_path, e)
            exit(1)

    def initialize_ocr(self):
        """初始化 OCR"""
        resource_path = self.config['resource']['path']
        self.ocr = PaddleOCR(
            use_angle_cls=False, lang="ch",
            det_model_dir=None, rec_model_dir=None,
            det_onnx_file=os.path.join(resource_path, self.config['resource']['det_model_path']),
            rec_onnx_file=os.path.join(resource_path, self.config['resource']['rec_model_path']),
            rec_char_dict_path=os.path.join(resource_path, self.config['resource']['charset_path']),
            show_log=False
        )
        logging.info("OCR initialized successfully")
        return self.ocr

    def start_emulator(self):
        """启动模拟器"""
        command = f'"{self.config["emulator"]["path"]}" {self.config["emulator"]["add_command"]}'
        subprocess.Popen(command, shell=True)
        logging.info("启动 MuMu Player 12，等待 %d 秒...", self.config['emulator']['wait_seconds'])
        time.sleep(self.config['emulator']['wait_seconds'])

    def connect_adb(self):
        """连接 ADB"""
        Toolkit.init_option("./")
        if not os.path.exists(self.config['adb']['path']):
            logging.error("ADB 文件不存在: %s", self.config['adb']['path'])
            exit(1)

        screencap_methods = (
            MaaAdbScreencapMethodEnum.RawByNetcat |
            MaaAdbScreencapMethodEnum.EmulatorExtras |
            MaaAdbScreencapMethodEnum.Encode
        )
        
        self.controller = AdbController(
            adb_path=self.config['adb']['path'],
            address=f"127.0.0.1:{self.config['adb']['port']}",
            screencap_methods=screencap_methods,
            input_methods=MaaAdbInputMethodEnum.Default,
            config={}
        )
        
        connect_job = self.controller.post_connection()
        connect_job.wait()
        if self.controller.connected:
            logging.info("ADB 连接成功")
            return self.controller
        logging.error("ADB 连接失败")
        exit(1)

    def launch_app(self):
        """启动应用"""
        app_job = self.controller.post_start_app(self.config['package_name'])
        app_job.wait()
        logging.info("已启动小黑盒应用")

    def initialize_all(self):
        """执行完整的初始化流程"""
        self.start_emulator()
        try:
            self.connect_adb()
        except Exception as e:
            logging.error("ADB 连接失败: %s", e)
            raise  # 或根据需求选择退出
        self.launch_app()
        self.initialize_ocr()
        return self.controller, self.ocr
    
if __name__ == "__main__":
    init = InitManager()
    controller, ocr = init.initialize_all()