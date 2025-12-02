import requests
import pandas as pd
import os
import sys

# 从 GitHub Secrets 获取 Webhook，如果没有则报错
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")

# 币安接口配置
SYMBOL = "BTCUSDT"
PERIOD = "5m"  # 关注5分钟线

def get_binance_data():
    """获取最近的大户多空比数据"""
    base_url = "https://fapi.binance.com"
    endpoint = "/futures/data/topLongShortAccountRatio"
    # 我们拉取最近5根K线足够了
    params = {"symbol": SYMBOL, "period": PERIOD, "limit": 5}
    
    try:
        response = requests.get(base_url + endpoint, params=params, timeout=10)
        response.raise_for_status()
        df = pd.DataFrame(response.json())
        df['longShortRatio'] = df['longShortRatio'].astype(float)
        # 转换时间戳方便调试
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_current_price():
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={SYMBOL}"
        resp = requests.get(url, timeout=10).json()
        return float(resp['price'])
    except:
        return 0.0

def send_discord_alert(title, color, description):
    if not WEBHOOK_URL:
        print("没有配置 Webhook，跳过发送")
        return

    data = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color, 
            "footer": {"text": "Binance Whale Monitor • GitHub Actions"}
        }]
    }
    requests.post(WEBHOOK_URL, json=data)

def main():
    print(f"开始检查 {SYMBOL} 数据...")
    df = get_binance_data()
    price = get_current_price()

    if df is None:
        sys.exit(1) # 获取失败，非正常退出

    # 取最近一根已收盘的柱子 (倒数第2个) 和它前面一根 (倒数第3个) 进行对比
    # 倒数第1个还在跳动，不稳定，所以我们看已经确定的过去5分钟
    current_candle = df.iloc[-2]
    prev_candle = df.iloc[-3]

    ratio_now = current_candle['longShortRatio']
    ratio_prev = prev_candle['longShortRatio']
    change = ratio_now - ratio_prev
    
    time_str = current_candle['timestamp']
    print(f"数据时间: {time_str} | 价格: {price} | 多空比: {ratio_prev} -> {ratio_now}")

    # --- 策略阈值 (可以根据需要调整) ---
    THRESHOLD = 0.01

    # 逻辑：
    if change < -THRESHOLD:
        msg = (f"**Whale离场 (Bearish)**\n"
               f"Time: {time_str}\n"
               f"Ratio Drop: {ratio_prev:.4f} -> **{ratio_now:.4f}**\n"
               f"Current Price: ${price}")
        send_discord_alert("大户多空比剧烈下降", 15158332, msg)
        print("触发看跌报警")
    
    elif change > THRESHOLD:
        msg = (f"**Whale吸筹 (Bullish)**\n"
               f"Time: {time_str}\n"
               f"Ratio Jump: {ratio_prev:.4f} -> **{ratio_now:.4f}**\n"
               f"Current Price: ${price}")
        send_discord_alert("大户多空比剧烈上升", 3066993, msg)
        print("触发看涨报警")
    else:
        print("无明显异动，无需报警")

if __name__ == "__main__":
    main()
