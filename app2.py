import pandas as pd
import dash
import os
from dash import dcc, html, State, callback_context
from dash.dependencies import Input, Output
from data_fetching import *
from chart_utils import *
import numpy as np
from top10gainer import create_dynamic_top_10_table

# ======================
# --- PHẦN 2: GIAO DIỆN DASH VÀ CALLBACK ---
# ======================

# Đọc dữ liệu master và khởi tạo ứng dụng
df_master = pd.read_csv('master_data.csv')
app = dash.Dash(__name__)

# Thiết kế layout
def create_top_10_by_exchange_tables():
    try:
        df = pd.read_csv('top_10_local_data.csv')
    except FileNotFoundError:
        return html.Div("")

    exchanges = ['HOSE', 'HNX', 'UPCOM']
    list_of_tabs = []

    for ex in exchanges:
        exchange_df = df[df['Sàn'] == ex].copy()
        top_10 = exchange_df.sort_values(by="Giá trị GD", ascending=False).head(10)
        
        table_component = dash_table.DataTable(
            columns=[
                {"name": "Mã CK", "id": "Mã CK"},
                {"name": "Giá trị GD (tỷ)", "id": "Giá trị GD (tỷ VND)"},
                {"name": "Giá đóng cửa", "id": "Giá đóng cửa"}
            ],
            data=(
                top_10.assign(**{
                    'Giá trị GD (tỷ VND)': (top_10['Giá trị GD'] / 1000).round(2),
                })
            ).to_dict('records'),
            style_cell={'textAlign': 'left', 'padding': '5px', 'fontSize': '12px'},
            style_header={
                'backgroundColor': 'rgb(240, 240, 240)',
                'fontWeight': 'bold'
            }
        )
        
        tab = dcc.Tab(label=ex, children=[
            html.Div(table_component, style={'marginTop': '10px'})
        ])
        
        list_of_tabs.append(tab)

    return html.Div([
        html.H4("Top 10 Cổ phiếu theo Sàn", style={'textAlign': 'center'}),
        dcc.Tabs(id="tabs-exchange", children=list_of_tabs)
    ])


app.layout = html.Div([
    dcc.Store(id='current-symbol-store'),

    html.H1("Thị trường chứng khoán Việt Nam", 
            style={'textAlign': 'center', 
                   'marginBottom': '20px', 
                   'width': '100%',
                   'fontSize': '45px'}),
    
    # --- THANH TÌM KIẾM ---
    html.Div([
        dcc.Dropdown(
            id='search-ticker-dropdown',
            options=get_ticker_list(),
            placeholder="Tìm kiếm mã cổ phiếu...",
            style={'width': '400px'}
        )
    ], style={'display': 'flex', 'justifyContent': 'center', 'marginBottom': '30px', 'width': '100%'}),

    # --- KHU VỰC CHÍNH: BẢN ĐỒ VÀ TOP 10 ---
    html.Div([
        # --- CỘT BÊN TRÁI: BẢN ĐỒ THỊ TRƯỜNG ---
        html.Div([
            html.H2("Bản đồ thị trường", style={'textAlign': 'center', 'marginBottom': '15px'}),
            html.Div([
                dcc.Dropdown(
                    id='dropdown-metric',
                    options=[
                        {'label': 'Vốn hóa thị trường', 'value': 'market_cap'},
                        {'label': 'Giá trị giao dịch', 'value': 'trading_value'}
                    ],
                    value='market_cap',
                    style={'width': '49%', 'display': 'inline-block'}
                ),
                dcc.Dropdown(
                    id='dropdown-sector',
                    options=[{'label': 'Tất cả các ngành', 'value': 'Tất cả các ngành'}] + 
                            [{'label': sector, 'value': sector} for sector in sorted(df_master['sector'].unique())],
                    value='Tất cả các ngành',
                    style={'width': '49%', 'float': 'right', 'display': 'inline-block'}
                )
            ], style={'marginBottom': '10px'}),
            dcc.Graph(id='treemap-graph'),
        ], style={'height': '500px','width': '70%', 'display': 'inline-block', 'verticalAlign': 'top', 'paddingRight': '20px'}),


        # --- CỘT BÊN PHẢI: TOP 10 DYNAMIC ---
        html.Div([
            html.H2("Top 10 Thống kê", style={'textAlign': 'center', 'marginBottom': '15px'}),
            
            # Dropdown chọn loại Top 10
            html.Div([
                dcc.Dropdown(
                    id='top10-type-dropdown',
                    options=[
                        {'label': 'Top 10 biến động giá', 'value': 'price_volatility'},
                        {'label': 'Top 10 Giá trị giao dịch lớn nhất', 'value': 'trading_value'}
                    ],
                    value='price_volatility',
                    style={'width': '100%', 'marginBottom': '10px'}
                ),
            ]),
            
            # Radio buttons chọn khoảng thời gian
            html.Div([
                dcc.RadioItems(
                    id='top10-period-radio',
                    options=[
                        {'label': 'Ngày', 'value': 'day'}, 
                        {'label': 'Tuần', 'value': 'week'}, 
                        {'label': 'Tháng', 'value': 'month'}
                    ],
                    value='day',
                    labelStyle={'display': 'inline-block', 'marginRight': '15px'},
                    style={'textAlign': 'center', 'marginBottom': '15px'}
                ),
            ]),
            
            # Nơi hiển thị bảng Top 10
            html.Div(id='top10-output', style={'marginTop': '10px'}),
            
        ], style={'height': '650px', 'width': '28%', 'display': 'inline-block', 'verticalAlign': 'top'})
    ], style={'marginBottom': '30px'}), 

    # --- KHU VỰC BIỂU ĐỒ NẾN ---
    html.Div(
        id='stock-chart-section',
        style={'display': 'none'},
        children=[
            html.H2("Lịch sử giá chi tiết", style={'textAlign': 'center', 'marginTop': '40px'}),
            dcc.RadioItems(
                id='time-filter-radio',
                options=[
                    {'label': '1M', 'value': '1M'}, {'label': '3M', 'value': '3M'}, 
                    {'label': '6M', 'value': '6M'}, {'label': '1Y', 'value': '1Y'}, 
                    {'label': '3Y', 'value': '3Y'}, {'label': 'All', 'value': 'All'}
                ],
                value='1Y',
                labelStyle={'display': 'inline-block', 'marginRight': '10px'},
                style={'textAlign': 'center', 'marginBottom': '20px'}
            ),
            dcc.Loading(
                id="loading-spinner",
                type="circle",
                children=html.Div(id='output-container-candlestick')
            )
        ]
    )
], style={'padding': '20px'})


# ======================
# --- CÁC HÀM CALLBACK ---
# ======================

@app.callback(
    Output('treemap-graph', 'figure'),
    [Input('dropdown-metric', 'value'),
     Input('dropdown-sector', 'value')]
)
def update_treemap_callback(selected_metric, selected_sector):
    dff = df_master.copy()
    if selected_sector != 'Tất cả các ngành':
        dff = dff[dff['sector'] == selected_sector]

    fig = plot_treemap(dff, selected_metric)

    if selected_metric == 'market_cap':
        color_col = 'price_change_pct'
    elif selected_metric == 'volume':
        color_col = 'volume_change_pct'
    else:
        color_col = 'price_change_pct'

    max_abs_change = dff[color_col].abs().max()
    if np.isnan(max_abs_change) or max_abs_change == 0:
        max_abs_change = 0.01

    custom_colorscale = [
        [0.0, "#8B0000"], [0.1, "#B22222"], [0.2, "#CD5C5C"], [0.3, "#F08080"], [0.4, "#F5C0A0"],
        [0.5, "#FFFFFF"], [0.6, "#A8E6A3"], [0.7, "#7CFC00"], [0.8, "#32CD32"], [0.9, "#228B22"], [1.0, "#006400"]
    ]

    if fig.data and hasattr(fig.data[0], 'parents'):
        trace = fig.data[0]
        labels = np.array(trace.labels)
        parents = np.array(trace.parents)
        all_parents = set(parents)
        new_colors = []

        for label, val, parent in zip(labels, trace.marker.colors, parents):
            if label in all_parents or label == "All":
                new_colors.append("#FFFFFF")
            else:
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    new_colors.append("#FFFFFF")
                else:
                    v = float(val)
                    frac = (v + max_abs_change) / (2 * max_abs_change)
                    frac = np.clip(frac, 0, 1)
                    hex_color = px.colors.sample_colorscale(custom_colorscale, [frac])[0]
                    new_colors.append(hex_color)

        trace.marker.colors = new_colors

    return fig


# Callback cập nhật bảng Top 10 dựa trên dropdown và period
@app.callback(
    Output('top10-output', 'children'),
    [Input('top10-type-dropdown', 'value'),
     Input('top10-period-radio', 'value')]
)
def update_top_10_table(metric_type, period):
    table = create_dynamic_top_10_table(
        df_master, 
        metric_type=metric_type, 
        period=period
    )
    return table


@app.callback(
    [Output('stock-chart-section', 'style'),
     Output('output-container-candlestick', 'children'),
     Output('current-symbol-store', 'data'),
     Output('search-ticker-dropdown', 'value')],
    [Input('search-ticker-dropdown', 'value'),
     Input('treemap-graph', 'clickData')]
)
def activate_and_update_stock_chart(search_symbol, click_data):
    ctx = callback_context
    if not ctx.triggered:
        return {'display': 'none'}, None, None, dash.no_update

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    symbol = None

    if triggered_id == 'search-ticker-dropdown' and search_symbol:
        symbol = search_symbol
    elif triggered_id == 'treemap-graph' and click_data:
        try:
            symbol = click_data['points'][0]['label']
        except (IndexError, KeyError):
            return {'display': 'none'}, None, None, dash.no_update
    
    if not symbol:
        return {'display': 'none'}, None, None, dash.no_update

    update_local_data(symbol)
    file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    if not os.path.exists(file_path):
        chart_content = html.Div(f"⚠️ Không tìm thấy file dữ liệu cho mã {symbol}.")
        return {'display': 'block'}, chart_content, symbol, symbol

    df_full = pd.read_csv(file_path, parse_dates=['Date'])
    df_full = df_full.iloc[:-1]
    
    if df_full.empty:
        chart_content = html.Div(f"⚠️ Dữ liệu cho mã {symbol} rỗng.")
        return {'display': 'block'}, chart_content, symbol, symbol
        
    reference_date = df_full['Date'].max()
    start_date = reference_date - pd.DateOffset(years=1)
    df_filtered = df_full[df_full["Date"] >= start_date].copy()
    
    fig = plot_stock_chart(df_filtered, symbol)
    chart_content = dcc.Graph(figure=fig)

    return {'display': 'block'}, chart_content, symbol, symbol


@app.callback(
    Output('output-container-candlestick', 'children', allow_duplicate=True),
    [Input('time-filter-radio', 'value')],
    [State('current-symbol-store', 'data')],
    prevent_initial_call=True
)
def filter_stock_chart_by_time(time_filter, symbol):
    if not symbol or not time_filter:
        return dash.no_update

    file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    df_full = pd.read_csv(file_path, parse_dates=['Date'])
    if df_full.empty:
        return html.Div(f"⚠️ Dữ liệu cho mã {symbol} rỗng.")

    reference_date = df_full['Date'].max()
    start_date = None
    if time_filter == "1M": 
        start_date = reference_date - pd.DateOffset(months=1)
    elif time_filter == "3M": 
        start_date = reference_date - pd.DateOffset(months=3)
    elif time_filter == "6M": 
        start_date = reference_date - pd.DateOffset(months=6)
    elif time_filter == "1Y": 
        start_date = reference_date - pd.DateOffset(years=1)
    elif time_filter == "3Y": 
        start_date = reference_date - pd.DateOffset(years=3)

    df_filtered = df_full[df_full["Date"] >= start_date].copy() if start_date else df_full.copy()
    
    if df_filtered.empty:
        return html.Div(f"⚠️ Không có dữ liệu cho {symbol} trong khoảng thời gian đã chọn.")

    fig = plot_stock_chart(df_full, symbol)
    
    return dcc.Graph(figure=fig)


# Chạy ứng dụng
if __name__ == "__main__":
    app.run(debug=True)