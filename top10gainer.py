import pandas as pd
from dash import dash_table, html
import os
import glob
import numpy as np

# --- HÀM UTILITY MỚI: XÁC ĐỊNH CHỈ MỤC THEO THỜI GIAN ---
def _get_period_params(period: str):
    """
    Xác định các chỉ số (index) cần thiết cho tính toán Ngày/Tuần/Tháng.
    Trả về (lookback_diff, lookback_sum)
    lookback_diff: Chỉ số để tính toán Price Volatility (ví dụ: Week -> index -8)
    lookback_sum: Số ngày để tính tổng Trading Value (ví dụ: Week -> 7 ngày)
    """
    if period == 'day':
        # Day: Difference giữa -1 và -2, Sum chỉ 1 ngày (-1)
        return 2, 1
    elif period == 'week':
        # Week: Difference giữa -1 và -8, Sum 7 ngày (-1 đến -7)
        return 8, 7
    elif period == 'month':
        # Month: Difference giữa -1 và -22, Sum 22 ngày (-1 đến -22)
        return 22, 22
    else: # Mặc định là Day
        return 2, 1
# ====================================================================
# --- HÀM MỚI: TÍNH TOÁN METRIC ĐỘNG TỪ FILE LOCAL ---
# ====================================================================
def calculate_top_10_metrics_data(master_df: pd.DataFrame, metric_type: str, period: str, data_dir: str = "data"):
    """
    Đọc dữ liệu lịch sử từ file local và tính toán chỉ số biến động giá (Price Volatility)
    HOẶC giá trị giao dịch (Trading Value) cho các khoảng thời gian khác nhau (Day/Week/Month).
    """
    file_paths = glob.glob(os.path.join(data_dir, "*.csv"))
    results = []
    master_symbols = set(master_df['symbol'].values)
    
    # Lấy tham số cho khoảng thời gian
    lookback_diff, lookback_sum = _get_period_params(period)

    for file_path in file_paths:
        symbol = os.path.basename(file_path).replace('.csv', '')
        if symbol not in master_symbols:
            continue
            
        try:
            # Chỉ đọc các cột cần thiết: Date, Close, GiaTriKhopLenh
            df = pd.read_csv(file_path, parse_dates=['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            df = df.iloc[:-1]  # Loại bỏ dòng cuối cùng nếu cần
            
            # Cần đủ số dòng để thực hiện tính toán
            if df.empty or len(df) < lookback_diff:
                continue
            
            # 2. Xử lý logic theo Metric Type
            value = 0
            
            if metric_type == 'price_volatility':
                # --- A. TOP 10 BIẾN ĐỘNG GIÁ ---
                
                # Giá đóng cửa mới nhất (index -1)
                latest_close = df.iloc[-1]['Close']
                # Giá đóng cửa tại thời điểm lookback (index -lookback_diff)
                previous_close = df.iloc[-lookback_diff]['Close']
                
                # Tính toán % biến động giá
                if previous_close > 0 and latest_close > 0:
                    # Lấy giá trị tuyệt đối cho 'Biến động mạnh nhất'
                    value = abs(latest_close - previous_close) / previous_close
                    
            elif metric_type == 'trading_value':
                # --- B. TOP 10 GIÁ TRỊ GIAO DỊCH ---
                
                # Lấy N dòng cuối cùng cho việc tính tổng
                # 🚀 FIX 1: Sử dụng cột 'GiaTriKhopLenh' từ file CSV thô
                sum_data = df['GiaTriKhopLenh'].tail(lookback_sum) 
                
                # Tính tổng giá trị giao dịch
                value = sum_data.sum()
            
            if value is not None and value >= 0:
                 results.append({
                    'symbol': symbol,
                    'metric_value': value,
                    'period': period
                })
            
        except IndexError:
            # Lỗi chỉ mục (IndexError) nếu không đủ dòng sau khi tail(N)
            continue
        except Exception:
            # Bỏ qua các lỗi khác (KeyError, chia cho 0, NaN, v.v.)
            continue 
            
    return pd.DataFrame(results)

# ====================================================================
# --- HÀM TẠO BẢNG TOP 10 MỚI (DYNAMIC) ---
# ====================================================================

def create_dynamic_top_10_table(master_df: pd.DataFrame, metric_type: str = 'price_volatility', period: str = 'day'):
    """
    Tạo bảng Dash DataTable Top 10 dựa trên chỉ số và khoảng thời gian được chọn.
    """
    
    # 1. Tính toán dữ liệu Metric
    df_metrics = calculate_top_10_metrics_data(master_df, metric_type, period)
    
    if df_metrics.empty:
        return html.Div([
            html.H4("Top 10 Loading...", style={'textAlign': 'center', 'marginTop': '20px'}),
            html.Div("⚠️ Không có đủ dữ liệu để tính toán.", style={'textAlign': 'center', 'color': 'red'})
        ])

    # 2. Merge với cột trading_value hiện tại (để hiển thị)
    df_display = df_metrics.merge(
        master_df[['symbol', 'trading_value']],
        on='symbol',
        how='left'
    )
    
    # 3. Chuẩn hóa và làm sạch
    df_display = df_display.dropna(subset=['metric_value', 'trading_value'])
    df_display = df_display.replace([float('inf'), -float('inf')], float('nan')).dropna(subset=['metric_value'])

    # 4. Sắp xếp và lấy Top 10
    top_10 = df_display.sort_values(by='metric_value', ascending=False).head(10)
    
    # 5. Định dạng tên cột và giá trị hiển thị
    
    if metric_type == 'price_volatility':
        title = f"Top 10 Cổ Phiếu Biến Động Giá Mạnh Nhất ({period.capitalize()})"
        metric_name = "% Biến Động"
        top_10['Formatted_Metric'] = (top_10['metric_value'] * 100).round(2).astype(str) + '%'
        color_style = {'color': 'blue', 'fontWeight': 'bold'}
    else: # trading_value
        title = f"Top 10 Cổ Phiếu Giá Trị Giao Dịch Lớn Nhất ({period.capitalize()})"
        metric_name = "Giá Trị GD (Tỷ)"
        top_10['Formatted_Metric'] = (top_10['metric_value'] / 1_000_000_000).round(2).astype(str) + ' Tỷ'
        color_style = {'color': '#006400', 'fontWeight': 'bold'}

    # Chuẩn bị cột hiển thị
    top_10 = top_10.rename(columns={'symbol': 'Mã CK', 'Formatted_Metric': metric_name})
    
    # Tên cột ID trong top_10 DataFrame
    KHO_CUA_TEN_COT = 'Giá Trị Khớp Lệnh (Tỷ VNĐ)' 
    
    # Tính toán và lưu vào tên cột đã fix
    top_10[KHO_CUA_TEN_COT] = (top_10['trading_value'] / 1_000_000_000).round(2).astype(str) + ' Tỷ'
    
    # Lọc lại các cột cần thiết cho bảng hiển thị
    # 🚀 FIX 2: Sửa lỗi chính tả Lenh -> Lệnh trong bước lọc cột
    top_gainers_display = top_10[['Mã CK', metric_name, KHO_CUA_TEN_COT]].copy()
    
    # 6. Tạo Dash DataTable Component
    table_component = dash_table.DataTable(
        id='dynamic-top-10-table',
        columns=[
            {"name": "Mã CK", "id": "Mã CK"},
            {"name": metric_name, "id": metric_name},
            # Sử dụng tên cột ID đã được sửa chính tả
            {"name": "Giá Trị Khớp Lệnh", "id": KHO_CUA_TEN_COT}, 
        ],
        data=top_gainers_display.to_dict('records'),
        style_header={
            'backgroundColor': '#E6F3E9' if metric_type == 'price_volatility' else '#F0F8FF', 
            'fontWeight': 'bold',
            'textAlign': 'center'
        },
        style_cell={
            'textAlign': 'center', 
            'padding': '8px', 
            'fontFamily': '"Times New Roman", Times, serif',
            'fontSize': '13px'
        },
        style_data_conditional=[
            {
                'if': {'column_id': metric_name},
                **color_style
            }
        ]
    )
    
    # 7. Trả về Div chứa tiêu đề và bảng
    return html.Div([
        html.H4(title, style={'textAlign': 'center', 'marginTop': '20px'}),
        table_component
    ], style={'padding': '10px', 'border': '1px solid #ccc', 'borderRadius': '5px'})

# def calculate_price_change_from_local_files(master_df: pd.DataFrame, data_dir: str = "data"):
#     """
#     Đọc 2 dòng cuối cùng của từng file CSV để tính toán % thay đổi giá (Close[-1] - Close[-2]) / Close[-2].
#     Chỉ trả về 'symbol' và 'price_change_pct'.
#     """
#     file_paths = glob.glob(os.path.join(data_dir, "*.csv"))
#     results = []
    
#     # Tạo set symbols từ master_df để lookup nhanh
#     master_symbols = set(master_df['symbol'].values)
    
#     for file_path in file_paths:
#         symbol = os.path.basename(file_path).replace('.csv', '')
            
#         if symbol not in master_symbols:
#             continue
            
#         try:
#             df = pd.read_csv(file_path, parse_dates=['Date'])
            
#             if df.empty or len(df) < 2:
#                 continue
                
#             df = df.sort_values('Date').tail(2)
            
#             latest_close = df.iloc[-2]['Close']
#             previous_close = df.iloc[-3]['Close']
            
#             if previous_close > 0 and latest_close > 0:
#                 price_change_pct = (latest_close - previous_close) / previous_close
#                 results.append({
#                     'symbol': symbol,
#                     'price_change_pct': price_change_pct
#                 })
            
#         except Exception:
#             # Bỏ qua mã lỗi
#             continue 
            
#     return pd.DataFrame(results)

# def create_top_10_gainers_from_local_files(master_df: pd.DataFrame):
#     """
#     Hàm chính tạo bảng Dash DataTable Top 10 Gainers, chỉ hiển thị 
#     Mã CK, % Thay đổi Giá và Giá Trị Khớp Lệnh (trading_value).
#     """
    
#     # 1. Tính toán % Thay đổi Giá từ file local
#     df_changes = calculate_price_change_from_local_files(master_df)
    
#     if df_changes.empty:
#         return html.Div([
#             html.H4("Top 10 Cổ phiếu Tăng giá Mạnh nhất", style={'textAlign': 'center', 'marginTop': '20px'}),
#             html.Div("⚠️ Không có đủ dữ liệu để tính toán % thay đổi giá.", style={'textAlign': 'center', 'color': 'red'})
#         ])

#     # 2. Merge với cột trading_value từ df_master
#     df_display = df_changes.merge(
#         master_df[['symbol', 'trading_value']],
#         on='symbol',
#         how='left'
#     )
    
#     # 3. Chuẩn hóa và làm sạch
#     df_display = df_display.dropna(subset=['price_change_pct', 'trading_value'])
#     df_display = df_display.replace([float('inf'), -float('inf')], float('nan')).dropna(subset=['price_change_pct'])

#     # 4. Đổi tên cột và sắp xếp
#     df_display = df_display.rename(columns={
#         'symbol': 'Mã CK',
#         'price_change_pct': '% Thay đổi Giá',
#         'trading_value': 'Giá Trị Khớp Lệnh' # Sẽ format sau
#     })
    
#     # Lấy Top 10 Tăng giá
#     top_gainers = df_display.sort_values(by='Giá Trị Khớp Lệnh', ascending=False).head(10)
    
#     # 5. Chuẩn bị dữ liệu để hiển thị (format)
#     # Format Giá Trị Khớp Lệnh sang Tỷ VNĐ
#     top_gainers['Giá Trị Khớp Lệnh (Tỷ VNĐ)'] = (top_gainers['Giá Trị Khớp Lệnh'] / 1_000_000_000).round(2)
#     top_gainers['Giá Trị Khớp Lệnh (Tỷ VNĐ)'] = top_gainers['Giá Trị Khớp Lệnh (Tỷ VNĐ)'].astype(str) + ' Tỷ'

#     # Format cột phần trăm: nhân 100 và làm tròn 2 chữ số thập phân
#     top_gainers['% Thay đổi Giá'] = (top_gainers['% Thay đổi Giá'] * 100).round(2).astype(str) + '%'

    
#     # Chỉ giữ lại 3 cột yêu cầu
#     top_gainers_display = top_gainers[['Mã CK', '% Thay đổi Giá', 'Giá Trị Khớp Lệnh (Tỷ VNĐ)']].copy()

    
#     # 6. Tạo Dash DataTable Component
#     table_component = dash_table.DataTable(
#         id='top-gainers-table-local',
#         columns=[
#             {"name": "Mã CK", "id": "Mã CK"},
#             {"name": "% Thay đổi Giá", "id": "% Thay đổi Giá"},
#             {"name": "Giá Trị Khớp Lệnh", "id": "Giá Trị Khớp Lệnh (Tỷ VNĐ)"},
#         ],
#         data=top_gainers_display.to_dict('records'),
#         style_header={
#             'backgroundColor': '#E6F3E9', 
#             'fontWeight': 'bold',
#             'textAlign': 'center'
#         },
#         style_cell={
#             'textAlign': 'center', 
#             'padding': '8px', 
#             'fontSize': '13px'
#         },
#         style_data_conditional=[
#             {
#                 'if': {'column_id': '% Thay đổi Giá'},
#                 'color': '#189E54', # Màu xanh lá
#                 'fontWeight': 'bold'
#             }
#         ]
#     )
    
#     # 7. Trả về Div chứa tiêu đề và bảng
#     return html.Div([
#         html.H4("Top 10 Cổ Phiếu Giao Dịch Nhiều Nhất", style={'textAlign': 'center', 'marginTop': '20px'}),
#         table_component
#     ], style={'padding': '10px', 'border': '1px solid #ccc', 'borderRadius': '5px'})

