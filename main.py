import requests
import os
import sys
import pandas as pd
from datetime import datetime

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
SYMBOL = "BTC-USD" 
# 定义什么是“大户”？
WHALE_THRESHOLD_USD = 20000

def get_recent_trades():
    """
    从 Coinbase 获取最近的成交记录 (Trade History)
    注意：这只能获取最近的 1000 笔，反映的是当前时刻的市场状态
    """
    url = f"https://api.exchange.coinbase.com/products/{SYMBOL}/trades"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception as e:
        print(f"Error fetching trades: {e}")
        return []

def calculate_whale_flow(trades):
    if not trades:
        return None

    df = pd.DataFrame(trades)
    
    # 数据清洗
    df['price'] = df['price'].astype(float)
    df['size'] = df['size'].astype(float)
    df['time'] = pd.to_datetime(df['time'])
    
    # 计算每单美元价值
    df['value_usd'] = df['price'] * df['size']
    
    # 筛选大单
    whales = df[df['value_usd'] >= WHALE_THRESHOLD_USD].copy()
    
    if whales.empty:
        # 如果当前没有大单，也返回基础信息
        return {
            "net_flow": 0, "buy_vol": 0, "sell_vol": 0, 
            "count": 0, "price": df.iloc[0]['price']
        }

    # 统计买卖
    buy_orders = whales[whales['side'] == 'buy']
    sell_orders = whales[whales['side'] == 'sell']
    
    buy_vol = buy_orders['size'].sum()
    sell_vol = sell_orders['size'].sum()
    
    # 净流量
    net_flow = buy_vol - sell_vol
    
    return {
        "net_flow": net_flow,
        "buy_vol": buy_vol,
        "sell_vol": sell_vol,
        "count": len(whales),
        "price": df.iloc[0]['price']
    }

def send_discord_alert(title, color, description):
    if not WEBHOOK_URL:
        print("未配置 Discord Webhook，跳过发送")
        return
    data = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color, 
            "footer": {"text": "Coinbase Daily Spot Check • Whale Monitor"},
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    try:
        requests.post(WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"发送 Discord 失败: {e}")

def main():
    print(f"[{datetime.now()}] 开始执行每日 Coinbase 抽查...")
    
    trades = get_recent_trades()
    data = calculate_whale_flow(trades)
    
    if not data:
        print("API 未返回数据")
        sys.exit(0)

    net_flow = data['net_flow']
    price = data['price']
    
    print(f"当前价格: ${price}")
    print(f"快照大单数: {data['count']} | 净流量: {net_flow:.4f} BTC")

    # === 每日播报逻辑 ===
    # 既然是一天一次，无论数据多少，最好都发一条消息，告知“我今天检查过了”
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    if net_flow > 0:
        title = f"每日定投时刻: 巨鲸正在买入"
        color = 3066993 # 绿色
        flow_emoji = "🟢"
    elif net_flow < 0:
        title = f"每日定投时刻: 巨鲸正在抛售"
        color = 15158332 # 红色
        flow_emoji = "🔴"
    else:
        title = f"📅 每日定投时刻: 市场平静"
        color = 9807270 # 灰色
        flow_emoji = "⚪"

    msg = (f"**{current_date} 市场快照 (Coinbase)**\n\n"
           f"**BTC 当前价格**: ${price}\n"
           f"{flow_emoji} **大单净流量**: {net_flow:+.2f} BTC\n"
           f"**大单成交笔数**: {data['count']} 笔\n"
           f"**主动买入**: {data['buy_vol']:.2f} BTC\n"
           f"**主动卖出**: {data['sell_vol']:.2f} BTC\n\n"
           f"*注：仅供参考*")
           
    send_discord_alert(title, color, msg)
    print("播报发送成功")

if __name__ == "__main__":
    main()
