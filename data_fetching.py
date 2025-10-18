import requests
import pandas as pd
import os
import numpy as np
from streamlit import html
from yahooquery import Ticker
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from dash import html, dash_table

DATA_DIR = "data"
EXCEL_FILE = "Data_Info_Vietnam.xlsx"

def get_stock_map():
    df = pd.read_excel(EXCEL_FILE, usecols=['Symbol', 'Exchange', 'Sector'])
    df = df.rename(columns={'Symbol': 'symbol', 'Exchange': 'exchange', 'Sector': 'sector'})
    df['symbol'] = df['symbol'].astype(str)
    df['exchange'] = df['exchange'].astype(str)
    df['sector'] = df['sector'].fillna('N/A').astype(str)
    return df


def get_market_info_yahoo(symbols: list):
    if not symbols:
        return pd.DataFrame(columns=['symbol', 'market_cap'])
    
    symbols_with_suffix = [s + '.VN' for s in symbols]
    data_list = [{'symbol': s} for s in symbols]
    
    try:
        tickers = Ticker(symbols_with_suffix, asynchronous=True, validate=True)
        summary_data = tickers.summary_detail
        price_data = tickers.price

        for item in data_list:
            symbol_vn = item['symbol'] + '.VN'
            summary_info = summary_data.get(symbol_vn, {})
            price_info = price_data.get(symbol_vn, {})
            
            market_cap = None
            if isinstance(summary_info, dict):
                market_cap = summary_info.get('marketCap')
            
            if not market_cap and isinstance(price_info, dict):
                market_cap = price_info.get('marketCap')

            item['market_cap'] = market_cap
            
    except Exception as e:
        print(f"Đã xảy ra lỗi nghiêm trọng khi lấy dữ liệu từ Yahoo Finance: {e}")
        for item in data_list:
            item.setdefault('market_cap', np.nan)

    return pd.DataFrame(data_list)


def get_ticker_list():
    stock_map = get_stock_map()
    if stock_map.empty:
        return []
    stock_map = stock_map.sort_values('symbol').reset_index(drop=True)
    options = [{'label': f"{row['symbol']} ({row['exchange']})", 'value': row['symbol']} for index, row in stock_map.iterrows()]
    return options


def get_tick_size(price, exch):
    exch = exch.upper()
    if exch == "HOSE":
        if price < 10000:
            return 10
        elif price < 50000:
            return 50
        else:
            return 100
    elif exch in ["HNX", "UPCOM"]:
        return 100
    else:
        return 10


def round_to_tick(price, tick):
    return np.round(price / tick) * tick

def apply_exchange_limits(df: pd.DataFrame, exchange: str) -> pd.DataFrame:
    if df.empty or 'Close' not in df.columns:
        return df
    for col in ['Open', 'High', 'Low', 'Close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    exch = exchange.upper()
    limits = {'HOSE': 0.07, 'HNX': 0.10, 'UPCOM': 0.15}
    limit = limits.get(exch, 0.07)
    df['Reference'] = df['Close'].shift(1)
    df['Ceiling'] = df['Reference'] * (1 + limit)
    df['Floor'] = df['Reference'] * (1 - limit)
    df['Tick_Size'] = 100
    if exch == 'HOSE':
        df.loc[(df['Reference'] >= 10000) & (df['Reference'] < 50000), 'Tick_Size'] = 50
        df.loc[df['Reference'] < 10000, 'Tick_Size'] = 10
    df['Ceiling'] = round_to_tick(df['Ceiling'], df['Tick_Size'])
    df['Floor'] = round_to_tick(df['Floor'], df['Tick_Size'])
    for col in ['Open', 'High', 'Low', 'Close']:
        if col in df.columns:
            df[col] = df[col].clip(lower=df['Floor'], upper=df['Ceiling'])
            df.loc[(df[col].isna()) | (df[col] == 0), col] = df['Floor'].where(~df['Floor'].isna(), df['Reference'])
    for col in ['Open', 'High', 'Low', 'Close']:
        if col in df.columns:
            df[col] = df[col].round().astype(int)
    df['High'] = df[['High', 'Open', 'Close']].max(axis=1)
    df['Low'] = df[['Low', 'Open', 'Close']].min(axis=1)
    df = df.drop(columns=['Reference', 'Ceiling', 'Floor', 'Tick_Size'])
    return df


def fetch_price_history_from_api(symbol: str, last_known_date: pd.Timestamp = None):
    print(f"Fetching API for {symbol}. Last known date: {last_known_date}")
    url = "https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    all_records = []
    page = 1
    page_size = 5000
    while True:
        try:
            resp = requests.get(url, params={"symbol": symbol, "page": page, "PageSize": page_size}, timeout=10)
            data = resp.json()
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            break
        if not data or "Data" not in data or not data["Data"]["Data"]:
            break
        records = data["Data"]["Data"]
        if last_known_date:
            temp_df = pd.DataFrame(records)
            temp_df['DateParsed'] = pd.to_datetime(temp_df['Ngay'], format="%d/%m/%Y", errors="coerce")
            if temp_df['DateParsed'].min() > last_known_date:
                all_records.extend(records)
            else:
                new_records = temp_df[temp_df['DateParsed'] > last_known_date]
                all_records.extend(new_records.drop(columns=['DateParsed']).to_dict('records'))
                break
        else:
            all_records.extend(records)
        if len(records) < page_size:
            break
        page += 1
        
    df = pd.DataFrame(all_records)

    if not df.empty:
        df = df.iloc[:-1]
        print(f"Đã loại bỏ dòng cuối cùng của dữ liệu API cho mã {symbol}.")
        
    return df

def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rename_map = {"Ngay": "Date", "GiaDongCua": "Close", "GiaMoCua": "Open", "GiaCaoNhat": "High", "GiaThapNhat": "Low", "KhoiLuongKhopLenh": "Volume"}
    df = df.rename(columns=rename_map)
    df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    for col in ["Close", "Open", "High", "Low"]:
        if col in df.columns:
            df[col] = (pd.to_numeric(df[col], errors="coerce") * 1000).round().astype(int)
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce", downcast="integer")
    df = df.dropna(subset=["Date", "Open", "High", "Low", "Close"], how="all")
    df = df.drop_duplicates(subset=['Date'], keep='first').reset_index(drop=True)
    return df

def update_local_data(symbol: str):
    DATA_DIR = "data"
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    stock_map = get_stock_map()
    stock_info = stock_map[stock_map['symbol'] == symbol]
    exchange = stock_info.iloc[0]['exchange'] if not stock_info.empty else "HOSE"
    
    file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    df_local = pd.DataFrame()
    last_known_date = None

    if os.path.exists(file_path):
        try:
            df_local = pd.read_csv(file_path, parse_dates=['Date'])
            if not df_local.empty:
                last_known_date = df_local['Date'].max()
        except pd.errors.EmptyDataError:
            pass 

    df_new_raw = fetch_price_history_from_api(symbol, last_known_date=last_known_date)
    
    if not df_new_raw.empty:
        df_new = preprocess_data(df_new_raw)
        df_combined = pd.concat([df_local, df_new], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=['Date'], keep='last').sort_values('Date').reset_index(drop=True)
        df_corrected = apply_exchange_limits(df_combined, exchange)
        
        df_corrected.to_csv(file_path, index=False)
        return df_corrected
        
    return df_local 


def get_latest_trading_date(sample_symbol='ACB'):
    print(f"Đang xác định ngày giao dịch mới nhất từ mã {sample_symbol}...")
    try:
        df = fetch_price_history_from_api(sample_symbol) 
        if not df.empty:
            df = preprocess_data(df)
            latest_date = df['Date'].max()
            print(f"Ngày giao dịch mới nhất được xác định là: {latest_date.strftime('%Y-%m-%d')}")
            return latest_date
    except Exception as e:
        print(f"Lỗi khi lấy ngày giao dịch mới nhất: {e}")
    return None


def create_master_data_intelligent_update():
    """
    Tạo hoặc cập nhật file master_data chỉ chứa các mã thuộc sàn HOSE.
    ✅ ĐÃ SỬA LỖI INDENTATION NGHIÊM TRỌNG
    """
    stock_map_full = get_stock_map()
    if stock_map_full.empty:
        print("Không lấy được danh sách cổ phiếu.")
        return pd.DataFrame()

    stock_map = stock_map_full[stock_map_full['exchange'] == 'HOSE'].copy()
    print(f"🔎 Đã lọc, chỉ xử lý {len(stock_map)} mã trên sàn HOSE.")
    
    output_file = "master_data.csv"
    
    all_symbols = stock_map['symbol'].tolist()
    save_interval = 20
    
    latest_trading_date = get_latest_trading_date()
    if latest_trading_date is None:
        print("Không thể xác định ngày giao dịch mới nhất. Dừng cập nhật.")
        return pd.read_csv(output_file) if os.path.exists(output_file) else pd.DataFrame()

    symbols_to_process = []
    if os.path.exists(output_file):
        try:
            df_existing = pd.read_csv(output_file, parse_dates=['date'])
            outdated_symbols = df_existing[df_existing['date'] < latest_trading_date]['symbol'].tolist()
            existing_symbols = set(df_existing['symbol'].unique())
            new_symbols = [s for s in all_symbols if s not in existing_symbols]
            symbols_to_process = sorted(list(set(outdated_symbols + new_symbols)))
            print(f"Phân tích file '{output_file}': {len(outdated_symbols)} mã cần cập nhật, {len(new_symbols)} mã mới.")
        except (pd.errors.EmptyDataError, FileNotFoundError):
            symbols_to_process = all_symbols
    else:
        print(f"File '{output_file}' không tồn tại. Sẽ xử lý toàn bộ {len(all_symbols)} mã HOSE.")
        symbols_to_process = all_symbols

    if not symbols_to_process:
        print("Tất cả dữ liệu HOSE đã được cập nhật. Hoàn tất!")
        return pd.read_csv(output_file)
        
    print(f"Tổng cộng có {len(symbols_to_process)} mã HOSE cần xử lý... Sẽ lưu file mỗi {save_interval} mã.")
    
    batch_data = []
    with ThreadPoolExecutor(max_workers=1) as executor:
        for i, symbol in enumerate(tqdm(symbols_to_process, desc="Processing symbols")):
            future = executor.submit(update_local_data, symbol)
            try:
                df_history = future.result(timeout=120)
                
                if df_history is not None and not df_history.empty:
                    last_date_in_history = df_history['Date'].max().strftime('%Y-%m-%d')
                    print(f"  [INFO] Mã {symbol}: Có {len(df_history)} dòng, ngày cuối cùng là {last_date_in_history}")
                else:
                    print(f"  [INFO] Mã {symbol}: Không có dữ liệu lịch sử.")
                    continue

                if df_history is not None and len(df_history) >= 2:
                    max_date_in_history = df_history['Date'].max()
                    df_confirmed = df_history[df_history['Date'] < max_date_in_history].copy()

                    if len(df_confirmed) >= 2:
                        df_confirmed_reset = df_confirmed.sort_values('Date').reset_index(drop=True)
                        
                        latest = df_confirmed_reset.iloc[-1]
                        previous = df_confirmed_reset.iloc[-2]

                        # ✅ SỬA LỖI: Kiểm tra dữ liệu hợp lệ
                        if pd.notna(latest['Close']) and pd.notna(previous['Close']) and \
                           pd.notna(latest['Volume']) and pd.notna(previous['Volume']):
                            
                            # Tính % Thay đổi Giá
                            if previous['Close'] > 0:
                                price_change_pct = (latest['Close'] - previous['Close']) / previous['Close']
                            else:
                                price_change_pct = 0
                            
                            # Tính % Thay đổi Khối lượng
                            if previous['Volume'] > 0:
                                volume_change_pct = (latest['Volume'] - previous['Volume']) / previous['Volume']
                            else:
                                volume_change_pct = 0

                            # Tính Giá trị giao dịch
                            latest_trading_value = latest['Close'] * latest['Volume']
                            previous_trading_value = previous['Close'] * previous['Volume']

                            # Tính % Thay đổi Giá trị giao dịch
                            if previous_trading_value > 0:
                                trading_value_change_pct = (latest_trading_value - previous_trading_value) / previous_trading_value
                            else:
                                trading_value_change_pct = 0
                            
                            # ✅ ĐÃ SỬA: batch_data.append() PHẢI Ở NGOÀI CÙNG
                            # Không bị phụ thuộc vào bất kỳ if/else nào ở trên
                batch_data.append({
                                'symbol': symbol, 
                                'date': latest['Date'], 
                                'close': latest['Close'],
                                'volume': latest['Volume'], 
                                'price_change_pct': price_change_pct,
                                'volume_change_pct': volume_change_pct,
                                'trading_value': latest_trading_value,
                                'trading_value_change_pct': trading_value_change_pct
                            })
                            
            except Exception as e:
                print(f"Lỗi khi xử lý mã {symbol}: {e}")
                continue

            # Lưu file theo batch
            if (i + 1) % save_interval == 0 or (i + 1) == len(symbols_to_process):
                if not batch_data:
                    print("\nCảnh báo: Batch rỗng, không có dữ liệu mới để cập nhật file master.")
                    continue

                print(f"\nĐã xử lý xong batch {len(batch_data)} mã. Bắt đầu cập nhật file master...")
                df_existing_current = pd.read_csv(output_file, parse_dates=['date']) if os.path.exists(output_file) else pd.DataFrame()
                df_processed = pd.DataFrame(batch_data)
                symbols_for_yahoo = df_processed['symbol'].tolist()
                print(f"--> [DEBUG] Các mã sẽ được gửi đến Yahoo: {symbols_for_yahoo[:5]}...")
                df_yahoo = get_market_info_yahoo(symbols_for_yahoo)
                print("\n--> [DEBUG] Dữ liệu trả về từ hàm get_market_info_yahoo (df_yahoo):")
                print(df_yahoo.head())
                print(f"Số dòng không NaN trong df_yahoo: {df_yahoo['market_cap'].notna().sum()} / {len(df_yahoo)}")
                df_final_processed = pd.merge(stock_map, df_processed, on='symbol', how='inner')
                if not df_yahoo.empty:
                    print("\n--> [DEBUG] Kiểm tra kiểu dữ liệu cột 'symbol':")
                    print(f"  - df_final_processed: {df_final_processed['symbol'].dtype}")
                    print(f"  - df_yahoo: {df_yahoo['symbol'].dtype}")
                    df_final_processed = pd.merge(df_final_processed, df_yahoo, on='symbol', how='left')
                else:
                    df_final_processed['market_cap'] = np.nan
                print("\n--> [DEBUG] Dữ liệu sau khi đã merge (df_final_processed):")
                print(df_final_processed[['symbol', 'close', 'market_cap']].head())
                print("-" * 50)
                if not df_existing_current.empty:
                    symbols_just_updated = df_final_processed['symbol'].tolist()
                    df_up_to_date = df_existing_current[~df_existing_current['symbol'].isin(symbols_just_updated)]
                    df_master = pd.concat([df_up_to_date, df_final_processed], ignore_index=True)
                else:
                    df_master = df_final_processed
                
                df_master = df_master.sort_values('symbol').reset_index(drop=True)
                df_master = df_master[~df_master.duplicated(subset=['symbol','sector'], keep='last')]
                df_master.to_csv(output_file, index=False)
                
                print(f"Đã cập nhật file '{output_file}' thành công. Tổng số mã hiện tại: {len(df_master)}.")
                batch_data = []

    print(f"\nHoàn tất toàn bộ quá trình!")
    return pd.read_csv(output_file) if os.path.exists(output_file) else pd.DataFrame()


def read_stock_data_for_date(stock_info, target_date, data_dir="data"):
    """
    Hàm đọc dữ liệu của MỘT cổ phiếu cho một ngày cụ thể từ file CSV đã xử lý.
    """
    symbol = stock_info['symbol']
    exchange = stock_info['exchange']
    file_path = os.path.join(data_dir, f"{symbol}.csv")

    if not os.path.exists(file_path):
        return None

    try:
        df = pd.read_csv(file_path, parse_dates=['Date'])
        daily_data = df[df['Date'] == target_date]
        
        if not daily_data.empty:
            record = daily_data.iloc[0]
            trading_value = record.get('Close', 0) * record.get('Volume', 0)
            
            return {
                "Mã CK": symbol,
                "Sàn": exchange,
                "Giá trị GD": trading_value,
                "Giá đóng cửa": record.get('Close', 0)
            }
    except (pd.errors.EmptyDataError, KeyError):
        return None
    return None


def generate_top_10_component_from_local():
    """
    Hàm này sẽ đọc dữ liệu từ các file CSV local đã được cập nhật,
    tổng hợp và trả về một component Dash chứa các bảng Top 10.
    """
    target_date = get_latest_trading_date()
    if target_date is None:
        return html.Div("Không thể xác định ngày giao dịch mới nhất.")
        
    print(f"🔎 Bắt đầu tổng hợp Top 10 từ file local cho ngày: {target_date.strftime('%d/%m/%Y')}")

    all_stocks_df = get_stock_map()
    stock_list = all_stocks_df.to_dict('records')
    
    all_daily_data = []

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(read_stock_data_for_date, stock, target_date) for stock in stock_list]
        
        for future in tqdm(futures, total=len(stock_list), desc="Đang đọc file CSV local"):
            result = future.result()
            if result:
                all_daily_data.append(result)

    if not all_daily_data:
        return html.Div(f"Không tìm thấy dữ liệu giao dịch cho ngày {target_date.strftime('%d/%m/%Y')} trong các file local.")

    print(f"\n✅ Tổng hợp hoàn tất. Tìm thấy {len(all_daily_data)} mã có dữ liệu.")
    final_df = pd.DataFrame(all_daily_data)
    
    exchanges = ['HOSE', 'HNX', 'UPCOM']
    list_of_tables = [html.H4(f"Top 10 Cổ phiếu có Giá trị Giao dịch Lớn nhất ({target_date.strftime('%d/%m/%Y')})", style={'textAlign': 'center'})]

    for ex in exchanges:
        exchange_df = final_df[final_df['Sàn'] == ex].copy()
        top_10 = exchange_df.sort_values(by="Giá trị GD", ascending=False).head(10)

        top_10_formatted = top_10.assign(**{
            'Giá trị GD (tỷ VND)': (top_10['Giá trị GD'] / 1_000_000_000).round(2),
            'Giá đóng cửa': top_10['Giá đóng cửa'].apply(lambda x: f"{x:,.0f}")
        })

        table_component = html.Div([
            html.H5(f"Sàn {ex}", style={'textAlign': 'center', 'marginTop': '20px'}),
            dash_table.DataTable(
                columns=[
                    {"name": "Mã CK", "id": "Mã CK"},
                    {"name": "Giá trị GD (tỷ)", "id": "Giá trị GD (tỷ VND)"},
                    {"name": "Giá đóng cửa", "id": "Giá đóng cửa"}
                ],
                data=top_10_formatted.to_dict('records'),
                style_cell={'textAlign': 'left', 'padding': '5px', 'fontSize': '12px', 'fontFamily': 'Arial'},
                style_header={
                    'backgroundColor': 'rgb(230, 230, 230)',
                    'fontWeight': 'bold'
                },
                style_data_conditional=[
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': 'rgb(248, 248, 248)'
                    }
                ]
            )
        ], style={'marginBottom': '20px', 'width': '32%', 'display': 'inline-block', 'padding': '0 5px'})
        
        list_of_tables.append(table_component)

    return html.Div(list_of_tables, style={'textAlign': 'center'})
    

if __name__ == '__main__':
    master_data = create_master_data_intelligent_update()
    top_10_component = generate_top_10_component_from_local()
    if not master_data.empty:
        print("\nXem trước 5 dòng dữ liệu đầu tiên:")
        print(master_data.head())