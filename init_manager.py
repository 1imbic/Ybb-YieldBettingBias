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
    """
    初始化管理器：负责系统启动流程，包括加载配置、启动模拟器、连接ADB、初始化OCR和启动小黑盒应用
    """
    def __init__(self, config_path='config.yaml'):
        """初始化配置"""
        self.config = self.load_config(config_path)

    def load_config(self, config_path):
        """从YAML文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                print(f"[初始化] 已加载配置文件: {config_path}")
                return config
        except Exception as e:
            print(f"[初始化] 加载配置文件失败 {config_path}: {e}")
            exit(1)

    def initialize_ocr(self):
        """初始化OCR模型：加载PaddleOCR模型用于识别界面文本"""
        resource_path = self.config['resource']['path']
        self.ocr = PaddleOCR(
            use_angle_cls=False, lang="ch",
            det_model_dir=None, rec_model_dir=None,
            det_onnx_file=os.path.join(resource_path, self.config['resource']['det_model_path']),
            rec_onnx_file=os.path.join(resource_path, self.config['resource']['rec_model_path']),
            rec_char_dict_path=os.path.join(resource_path, self.config['resource']['charset_path']),
            show_log=False
        )
        print("[初始化] OCR模型初始化成功")
        return self.ocr

    def start_emulator(self):
        """启动模拟器：调用配置中指定的模拟器路径启动模拟器"""
        command = f'"{self.config["emulator"]["path"]}" {self.config["emulator"]["add_command"]}'
        subprocess.Popen(command, shell=True)
        print(f"[初始化] 启动模拟器 MuMu Player 12，等待 {self.config['emulator']['wait_seconds']} 秒...")
        time.sleep(self.config['emulator']['wait_seconds'])

    def connect_adb(self):
        """连接ADB：建立与模拟器的ADB连接，用于后续的界面控制"""
        Toolkit.init_option("./")
        if not os.path.exists(self.config['adb']['path']):
            print(f"[初始化] ADB文件不存在: {self.config['adb']['path']}")
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
        
        print(f"[初始化] 尝试ADB连接到 127.0.0.1:{self.config['adb']['port']}...")
        connect_job = self.controller.post_connection()
        connect_job.wait()
        if self.controller.connected:
            print("[初始化] ADB连接成功")
            return self.controller
        print("[初始化] ADB连接失败")
        exit(1)

    def launch_app(self):
        """启动应用：通过ADB命令启动小黑盒应用"""
        app_job = self.controller.post_start_app(self.config['package_name'])
        app_job.wait()
        print(f"[初始化] 已启动小黑盒应用 {self.config['package_name']}")

    def initialize_all(self):
        """执行完整的初始化流程：启动模拟器 -> 连接ADB -> 启动应用 -> 初始化OCR"""
        print("[初始化] 开始完整初始化流程...")
        self.start_emulator()
        try:
            self.connect_adb()
        except Exception as e:
            print(f"[初始化] ADB连接失败: {e}")
            raise
        self.launch_app()
        self.initialize_ocr()
        print("[初始化] 初始化流程完成，返回controller和ocr实例")
        return self.controller, self.ocr
    
if __name__ == "__main__":
    init = InitManager()
    controller, ocr = init.initialize_all()