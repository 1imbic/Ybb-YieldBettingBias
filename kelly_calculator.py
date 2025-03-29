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
