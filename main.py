import requests
import os
import sys
import pandas as pd
from datetime import datetime

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
SYMBOL = "BTC-USD" 
# 定义什么是“大户”？这里设定为单笔成交大于 20,000 美元
# Coinbase 散户多，2万刀一笔已经算是有力度的资金了
WHALE_THRESHOLD_USD = 20000

def get_recent_trades():
    """
    从 Coinbase 获取最近的成交记录 (Trade History)
    API: Public, 无需 Key, 美国 IP 友好
    """
    url = f"https://api.exchange.coinbase.com/products/{SYMBOL}/trades"
    try:
        # 获取最近 1000 笔交易 (Coinbase 默认分页限制，但这足够分析最近几分钟了)
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception as e:
        print(f"Error fetching trades: {e}")
        return []

def calculate_whale_flow(trades):
    """
    核心算法：计算大单净买入量 (Net Flow)
    """
    if not trades:
        return None

    df = pd.DataFrame(trades)
    
    # 数据清洗
    df['price'] = df['price'].astype(float)
    df['size'] = df['size'].astype(float)
    df['time'] = pd.to_datetime(df['time'])
    
    # 计算每单的美元价值
    df['value_usd'] = df['price'] * df['size']
    
    # === 关键步骤：只看大单 ===
    # 筛选出价值 > 阈值的交易
    whales = df[df['value_usd'] >= WHALE_THRESHOLD_USD].copy()
    
    if whales.empty:
        return {"net_flow": 0, "buy_vol": 0, "sell_vol": 0, "count": 0, "price": df.iloc[0]['price']}

    # 统计买卖方向
    # Coinbase 的 side='buy' 意味着 taker 是买家 (主动买入)
    # side='sell' 意味着 taker 是卖家 (主动砸盘)
    buy_orders = whales[whales['side'] == 'buy']
    sell_orders = whales[whales['side'] == 'sell']
    
    buy_vol = buy_orders['size'].sum()
    sell_vol = sell_orders['size'].sum()
    
    # 净流量 = 主动买入 - 主动卖出
    net_flow = buy_vol - sell_vol
    
    return {
        "net_flow": net_flow,      # 净流入BTC数量
        "buy_vol": buy_vol,        # 大单买入总量
        "sell_vol": sell_vol,      # 大单卖出总量
        "count": len(whales),      # 大单笔数
        "price": df.iloc[0]['price'] # 最新价格
    }

def send_discord_alert(title, color, description):
    if not WEBHOOK_URL:
        return
    data = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color, 
            "footer": {"text": "Coinbase Whale Order Flow • Custom Algo"}
        }]
    }
    requests.post(WEBHOOK_URL, json=data)

def main():
    print(f"开始计算 Coinbase ({SYMBOL}) 大单资金流...")
    print(f"大户门槛: > ${WHALE_THRESHOLD_USD}")
    
    trades = get_recent_trades()
    data = calculate_whale_flow(trades)
    
    if not data:
        print("无数据或无大单")
        sys.exit(0)

    net_flow = data['net_flow']
    price = data['price']
    
    print(f"当前价格: ${price}")
    print(f"大单统计: {data['count']} 笔 | 净流量: {net_flow:.4f} BTC")
    print(f"买入: {data['buy_vol']:.4f} | 卖出: {data['sell_vol']:.4f}")

    # === 策略阈值 ===
    # 如果短时间内净买入/卖出超过 5 BTC (根据Coinbase流动性调整)
    ALERT_TRIGGER_BTC = 5.0 

    if net_flow > ALERT_TRIGGER_BTC:
        msg = (f"**大户正在扫货 (Strong Buying)**\n"
               f"Coinbase 出现密集大单买入！\n"
               f"Net Flow: **+{net_flow:.2f} BTC**\n"
               f"Price: ${price}\n"
               f"Whale Orders: {data['count']} trades > ${WHALE_THRESHOLD_USD}")
        send_discord_alert("巨鲸买入信号", 3066993, msg) # 绿色

    elif net_flow < -ALERT_TRIGGER_BTC:
        msg = (f"**大户正在砸盘 (Strong Selling)**\n"
               f"Coinbase 出现密集大单抛售！\n"
               f"Net Flow: **{net_flow:.2f} BTC**\n"
               f"Price: ${price}\n"
               f"Whale Orders: {data['count']} trades > ${WHALE_THRESHOLD_USD}")
        send_discord_alert("巨鲸抛售信号", 15158332, msg) # 红色
    else:
        print("大户资金流向不明显，无报警。")

if __name__ == "__main__":
    main()
