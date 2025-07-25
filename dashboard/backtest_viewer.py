import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import json
from datetime import datetime
import altair as alt
import os

# Set page config
st.set_page_config(
    page_title="Nifty Options Backtest Results",
    page_icon="📈",
    layout="wide"
)

# Get the absolute path to the project root
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = PROJECT_ROOT / "backtesting" / "results"

# Debug information
st.sidebar.write("Debug Information:")
st.sidebar.write(f"Project Root: {PROJECT_ROOT}")
st.sidebar.write(f"Results Directory: {RESULTS_DIR}")
st.sidebar.write(f"Results Dir Exists: {RESULTS_DIR.exists()}")
if RESULTS_DIR.exists():
    st.sidebar.write("Files in results directory:")
    for f in RESULTS_DIR.glob("*"):
        st.sidebar.write(f"- {f.name}")

def load_backtest_results(results_dir: Path = RESULTS_DIR):
    """Load all backtest results from the results directory."""
    results = []
    
    # Get all metrics files
    metrics_files = list(results_dir.glob("metrics_*.json"))
    st.sidebar.write(f"Found {len(metrics_files)} metrics files")
    
    for metrics_file in metrics_files:
        # Get corresponding trades file (with .csv extension)
        trades_file = results_dir / f"trades_{metrics_file.name[8:-5]}.csv"  # Changed from .json to .csv
        st.sidebar.write(f"Looking for trades file: {trades_file.name}")
        st.sidebar.write(f"Trades file exists: {trades_file.exists()}")
        
        if not trades_file.exists():
            continue
            
        try:
            # Load metrics
            with open(metrics_file) as f:
                metrics = json.load(f)
                
            # Load trades
            trades = pd.read_csv(trades_file)
            trades['timestamp'] = pd.to_datetime(trades['timestamp'])
            
            results.append({
                'metrics': metrics,
                'trades': trades,
                'run_id': metrics_file.name[8:-5]  # Remove 'metrics_' and '.json'
            })
        except Exception as e:
            st.sidebar.error(f"Error loading files: {str(e)}")
    
    return results

def calculate_cumulative_metrics(trades_df):
    """Calculate cumulative metrics from trades."""
    trades_df = trades_df.copy()
    trades_df['cumulative_trades'] = range(1, len(trades_df) + 1)
    
    # Calculate P&L (assuming entry and exit pairs)
    trades_df['trade_pnl'] = 0
    for i in range(0, len(trades_df), 2):
        if i + 1 < len(trades_df):
            entry_price = trades_df.iloc[i]['avg_fill_price']
            exit_price = trades_df.iloc[i + 1]['avg_fill_price']
            pnl = (exit_price - entry_price) * trades_df.iloc[i]['filled_quantity']
            trades_df.iloc[i:i+2, trades_df.columns.get_loc('trade_pnl')] = pnl
    
    trades_df['cumulative_pnl'] = trades_df['trade_pnl'].cumsum()
    
    return trades_df

def main():
    st.title("📈 Nifty Options Backtest Results")
    
    # Load results
    results = load_backtest_results()
    
    if not results:
        st.warning("No backtest results found. Run a backtest first!")
        return
    
    # Sidebar - Select backtest run
    st.sidebar.header("Select Backtest Run")
    selected_run = st.sidebar.selectbox(
        "Choose a backtest run:",
        options=[r['run_id'] for r in results],
        format_func=lambda x: datetime.strptime(x, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    )
    
    # Get selected result
    result = next(r for r in results if r['run_id'] == selected_run)
    metrics = result['metrics']
    trades = result['trades']
    
    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Trades", metrics['total_trades'])
    with col2:
        st.metric("Total P&L", f"₹{metrics['total_pnl']:,.2f}")
    with col3:
        st.metric("Win Rate", f"{metrics['win_rate']:.1f}%")
    with col4:
        st.metric("Avg Profit/Trade", f"₹{metrics['avg_profit_per_trade']:,.2f}")
    
    # Calculate cumulative metrics
    trades_with_metrics = calculate_cumulative_metrics(trades)
    
    # P&L Chart
    st.subheader("Cumulative P&L")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trades_with_metrics['timestamp'],
        y=trades_with_metrics['cumulative_pnl'],
        mode='lines+markers',
        name='Cumulative P&L'
    ))
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="P&L (₹)",
        hovermode='x unified'
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Trade Distribution
    st.subheader("Trade Distribution")
    col1, col2 = st.columns(2)
    
    with col1:
        # Trade prices histogram
        fig_hist = px.histogram(
            trades,
            x='avg_fill_price',
            title='Trade Price Distribution',
            nbins=20
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    
    with col2:
        # Trade volume by hour
        trades['hour'] = trades['timestamp'].dt.hour
        hourly_volume = trades.groupby('hour').size().reset_index(name='count')
        fig_hour = px.bar(
            hourly_volume,
            x='hour',
            y='count',
            title='Trade Volume by Hour'
        )
        st.plotly_chart(fig_hour, use_container_width=True)
    
    # Raw trade data
    st.subheader("Trade List")
    st.dataframe(
        trades.style.format({
            'avg_fill_price': '₹{:,.2f}',
            'filled_quantity': '{:,.0f}'
        }),
        use_container_width=True
    )
    
    # Backtest Parameters
    st.sidebar.subheader("Backtest Parameters")
    st.sidebar.text(f"Start: {metrics['start_time']}")
    st.sidebar.text(f"End: {metrics['end_time']}")
    st.sidebar.text(f"Run Time: {datetime.strptime(selected_run, '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main() 