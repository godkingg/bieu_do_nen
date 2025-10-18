
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import numpy as np

# ======================
# --- BIỂU ĐỒ NẾN ---
# ======================
def plot_stock_chart(df: pd.DataFrame, symbol: str):
    df = df.reset_index(drop=True)
    # df = df.iloc[:-1]
    # === 1️⃣ TÍNH TOÁN CÁC ĐƯỜNG TRUNG BÌNH & BOLLINGER BANDS ===
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['MA100'] = df['Close'].rolling(window=100).mean()

    # Bollinger Bands (sử dụng MA20 theo thông lệ)
    window = 20
    df['MA20'] = df['Close'].rolling(window=window).mean()
    df['STD20'] = df['Close'].rolling(window=window).std()
    df['BB_Upper'] = df['MA20'] + 2 * df['STD20']
    df['BB_Lower'] = df['MA20'] - 2 * df['STD20']

    # === 2️⃣ TÍNH TOÁN MACD ===
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Histogram'] = df['MACD'] - df['Signal']

    # === 3️⃣ DỮ LIỆU HOVER ===
    custom_data_for_hover = df[[
        'Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'MA50', 'MA100', 
        'BB_Upper', 'BB_Lower', 'MACD', 'Signal'
    ]].to_numpy()

    custom_data_for_hover[:, 0] = df['Date'].dt.strftime('%Y-%m-%d')

    # === 4️⃣ TẠO SUBPLOT 2 HÀNG (giá + MACD) ===
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        specs=[
            [{"secondary_y": True}],  # Hàng 1: Giá + Volume
            [{"secondary_y": False}]  # Hàng 2: MACD
        ],
        row_heights=[0.7, 0.3],
        vertical_spacing=0.1,
        subplot_titles=(f'{symbol} - Giá và Khối lượng', 'MACD Indicator')
    )

    # === 5️⃣ BIỂU ĐỒ NẾN ===
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="Giá",
        increasing_line_color="#189E54", decreasing_line_color="#C7211E",
        hoverinfo='none'
    ), row=1, col=1, secondary_y=False)

    # === Trace vô hình để điều khiển hover ===
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Close'],
        mode='lines',
        line=dict(color='rgba(0,0,0,0)', width=0),
        showlegend=False,
        customdata=custom_data_for_hover,
        hovertemplate=(
            "<b>Date: %{customdata[0]}</b>"
            "<br>Open: %{customdata[1]:,.0f}"
            "<br>High: %{customdata[2]:,.0f}"
            "<br>Low: %{customdata[3]:,.0f}"
            "<br>Close: %{customdata[4]:,.0f}"
            "<br>Volume: %{customdata[5]:,.0f}"
            "<br>MA50: %{customdata[6]:,.1f}"
            "<br>MA100: %{customdata[7]:,.1f}"
            "<br>BB Upper: %{customdata[8]:,.1f}"
            "<br>BB Lower: %{customdata[9]:,.1f}"
            "<br>MACD: %{customdata[10]:,.2f}"
            "<br>Signal: %{customdata[11]:,.2f}"
            "<extra></extra>"
        )
    ), row=1, col=1)

    # === 6️⃣ ĐƯỜNG MA, BB ===
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], mode='lines', name='MA50',
        line=dict(color='orange', width=1.5), hoverinfo='none'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA100'], mode='lines', name='MA100',
        line=dict(color='blue', width=1.5), hoverinfo='none'), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], mode='lines', name='BB Upper',
        line=dict(color='rgba(128,0,128,0.7)', width=1, dash='dash'), hoverinfo='none'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], mode='lines', name='BB Lower',
        line=dict(color='rgba(255,0,0,0.7)', width=1, dash='dash'), hoverinfo='none'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], mode='lines', name='MA20',
        line=dict(color='#fc03a9', width=1.5), hoverinfo='none'), row=1, col=1)

    # === 7️⃣ VOLUME ===
    if 'Volume' in df.columns and not df['Volume'].isna().all():
        colors_volume = [
            '#C7211E' if row['Close'] < row['Open'] else '#189E54'
            for _, row in df.iterrows()
        ]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"], name="Khối lượng",
            marker=dict(color=colors_volume, opacity=0.5),
            hoverinfo='none'
        ), row=1, col=1, secondary_y=True)

    # === 8️⃣ MACD ===
    fig.add_trace(go.Bar(
        x=df.index, y=df['Histogram'], name='Histogram',
        marker_color=df['Histogram'].apply(lambda x: '#189E54' if x >= 0 else '#C7211E'),
        opacity=0.6
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD'], mode='lines', name='MACD',
        line=dict(color='blue', width=1.5)
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Signal'], mode='lines', name='Signal',
        line=dict(color='orange', width=1.5)
    ), row=2, col=1)

    # === 9️⃣ CẬP NHẬT TRỤC & GIAO DIỆN ===
    num_ticks = 15
    tick_spacing = max(1, len(df) // num_ticks)
    tick_indices = df.index[::tick_spacing]
    tick_dates = df['Date'].dt.strftime('%Y-%m-%d')[::tick_spacing]

    min_price = df["Low"].min()
    max_price = df["High"].max()
    price_range = max_price - min_price
    padding = price_range * 0.1
    y_max = max_price + padding
    y_min = max(0, min_price - padding)

    max_volume = df['Volume'].max() if 'Volume' in df.columns else 0
    volume_y_max = max_volume * 5

    fig.update_xaxes(tickvals=tick_indices, ticktext=tick_dates,
        showgrid=True, gridwidth=1, gridcolor='#E5E5E5',
        showline=True, linewidth=2, linecolor='black')

    fig.update_yaxes(title_text="Giá (VNĐ)", range=[y_min, y_max],
        showgrid=True, gridwidth=1, gridcolor='#E5E5E5',
        showline=True, linewidth=2, linecolor='black',
        side='left', secondary_y=False, row=1, col=1)
    fig.update_yaxes(title_text="Khối lượng", range=[0, volume_y_max],
        fixedrange=True, showgrid=False, showline=True,
        linewidth=2, linecolor='black', side='right', secondary_y=True, row=1, col=1)
    fig.update_yaxes(title_text="MACD", showgrid=True, row=2, col=1)

    fig.update_layout(
        height=900, hovermode='x unified', xaxis_rangeslider_visible=False,
        plot_bgcolor='white', paper_bgcolor='white',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    return fig


# ======================
# --- BIỂU ĐỒ TREEMAP ---
# ======================

def plot_treemap(df: pd.DataFrame, metric: str):
    # Khai báo biến
    values_col, color_col, hovertemplate_str = '', '', ''
    df = df.drop_duplicates(subset=['symbol'])
    # Thiết lập linh hoạt
    if metric == 'market_cap':
        values_col = 'market_cap'
        color_col = 'price_change_pct'
        hovertemplate_str = ('<b>%{label}</b><br>'
                             'Vốn hóa: %{value:,.0f} VNĐ<br>'
                             '% Thay đổi giá: %{customdata[0]:.2%}'
                             '<extra></extra>')

    elif metric == 'volume':
        values_col = 'volume'
        color_col = 'volume_change_pct'
        hovertemplate_str = ('<b>%{label}</b><br>'
                             'Khối lượng GD: %{value:,.0f}<br>'
                             '% Thay đổi KLGD: %{customdata[0]:.2%}'
                             '<extra></extra>')
    else:
        values_col = 'market_cap'
        color_col = 'price_change_pct'
        hovertemplate_str = ('<b>%{label}</b><br>'
                             'Vốn hóa: %{value:,.0f} VNĐ<br>'
                             '% Thay đổi giá: %{customdata[0]:.2%}'
                             '<extra></extra>')

    # Xác định phạm vi màu động dựa trên dữ liệu
    max_abs_change = df[color_col].abs().max()
    if np.isnan(max_abs_change) or max_abs_change == 0:
        max_abs_change = 0.01  # tránh lỗi chia 0

    # Tùy chỉnh thang màu gồm 11 điểm: 5 đỏ - trắng - 5 xanh
    custom_colorscale = [
        [0.0, "#8B0000"],   # đỏ đậm
        [0.1, "#B22222"],
        [0.2, "#CD5C5C"],
        [0.3, "#F08080"],
        [0.4, "#F5C0A0"],
        [0.5, "#FFFFFF"],   # trung tính (0)
        [0.6, "#A8E6A3"],
        [0.7, "#7CFC00"],
        [0.8, "#32CD32"],
        [0.9, "#228B22"],
        [1.0, "#006400"],   # xanh đậm
    ]

    # Vẽ biểu đồ treemap
    fig = px.treemap(
        df,
        path=[px.Constant("Tất cả"), 'sector', 'symbol'],
        values=values_col,
        color=color_col,
        color_continuous_scale=custom_colorscale,
        range_color=[-max_abs_change, max_abs_change],
        color_continuous_midpoint=0,
        custom_data=[color_col],
    )

    # Hover & text hiển thị
    fig.update_traces(
        hovertemplate=hovertemplate_str,
        texttemplate="<b>%{label}</b><br>%{customdata[0]:.2%}"
    )

    # Giao diện gọn gàng
    fig.update_layout(
        margin=dict(t=25, l=25, r=25, b=25),
        coloraxis_colorbar=dict(
            title="",
            tickformat=".0%",
            lenmode="fraction", len=0.8,
            thickness=15,
            yanchor="middle", y=0.5
        )
    )

    return fig