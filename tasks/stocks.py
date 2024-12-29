""" 📉 Functions to get stock prices and trends"""

import base64
from io import BytesIO
import seaborn as sns
import yfinance as yf
from matplotlib import pyplot as plt
import logging
import pandas as pd

def research_stock_history(ticker):
    """Retrieve the previous quarter of stock prices
    
    ARGUMENTS
    ticker (str): The abbreviation of the stock
    
    RETURNS
    stock_df (DataFrame): Previous month's stock prices
    """
    stock = yf.Ticker(ticker)
    
    # Get stock name
    # This is the series name that will be displayed in plot.
    stock_info = stock.info
    if "shortName" in stock_info:
        stock_name = stock.info["shortName"]
    elif "longName" in stock_info:
        stock_name = stock.info["longName"]
    else:
        stock_name = ticker
    if len(stock_name)<4: # If name is blank or unexpectedly short, use ticker
        stock_name = ticker

    # Get price series
    # By default we get the last quarter, the max we may need
    stock_df = (
        stock
        .history(period="3mo")
        .reset_index() #.reset_index()[["
        .assign(
            date = lambda df: df["Date"].dt.strftime("%m-%d"),
        )
        [["date", "Close"]]
    )
    stock_df[stock_name] = stock_df["Close"]
    
    return (
        stock_df
        .set_index(["date"])
        .drop(columns=["Close"])
    )


def research_stock_histories(tickers):
    """Get previous quarter prices for a list of stocks
    
    ARGUMENTS
    tickers (list of str): The abbreviation (ticker) of each stock  

    RETURNS
    stocks_df (DataFrame): Previous month's prices, with each stock as a column and mon-day (str) as index
    """
    
    stocks_l = [research_stock_history(ticker) for ticker in tickers]
    stocks_df = pd.concat(stocks_l, axis=1)
    stocks_df = stocks_df.loc[:, stocks_df.max().sort_values(ascending=False).index] # Sort biggest ticker first
    return stocks_df


def plot_stocks(stocks_df, history="quarter", dev_mode=False):
    """Create a plot for stock prices.
    
    ARGUMENTS
    stocks_df (DataFrame): Previous month's prices, with each stock as a column and mon-day (str) as index
    history (str): How long in the past to plot. "quarter", "month", "week"
    dev_mode (bool): If we're in dev/debug, output the plots to local files too.
    
    RETURNS
    png_b64 (str): The PNG image as base64

    """
    if history=="quarter":
        # Tick for every 30 days, and ensure we include last day. Set de-dups if necessary
        ticks = pd.Index(
            set(
                list(stocks_df.index[::30])[0:-1] + [stocks_df.index[-1]]
            )
        )
    elif history=="month":
        stocks_df = stocks_df.tail(30)
        # Tick for every week, and ensure we include last day. Set de-dups if necessary                  
        ticks = pd.Index(
            set(
                list(stocks_df.index[::7])[0:-1] + [stocks_df.index[-1]]
            )
        ) 
    elif history=="week":
        stocks_df = stocks_df.tail(7)
        # A tick for every day
        ticks = list(stocks_df.index) 
    else:
        logging.warning(f"Unexpected value of `history` in plot_stocks(): {history}")
        return None

    fig = plt.figure(figsize=(8,5))
    plt.style.use("dark_background")
    sns.lineplot(data=stocks_df, palette="husl", dashes=False, lw=4)
    sns.despine()
    plt.tight_layout()
    plot_max_y = stocks_df.iloc[:, 0].max() # Max of biggest ticker
    _ = plt.ylim(0, 1.2 * plot_max_y) # Max of biggest ticker + 20%

    # Plot tick marks
    plt.xticks(
        ticks, # Set() de-dups if necessary
        rotation=45,
        horizontalalignment='right',
        fontweight='light'
    )
    ax = plt.gca() # Get current axis

    # Add text labels
    for stock_i, stock_name in enumerate(stocks_df.columns):
        ticker_s = stocks_df[stock_name].dropna()

        # Add stock name
        ax.annotate(
            xy=(ticker_s.index[-1], ticker_s.iloc[-1]),
            xytext=(30,-5),
            textcoords='offset points',
            text=ticker_s.name, # The name of the Series = full name of stock, else ticker
            fontsize=20,
            color=ax.lines[stock_i].get_color(),
            ha='left',
        )
        
        # Add data labels
        for i in [0, -1]:
            ax.annotate(
                xy=(ticker_s.index[i], ticker_s.iloc[i]),
                xytext=(0, 20), # Place text 20 points above each data point
                textcoords='offset points',
                text=int(round(ticker_s.iloc[i],0)),
                fontsize=18 if i ==-1 else 14,
                color=ax.lines[stock_i].get_color(),
                ha='center',
                va='top'
            )

    plt.legend([],[], frameon=False) # Remove legend
    ax.set_xlabel(None) # Remove "Date" name of X axis
    
    # Get raw image
    png_bytes = BytesIO()
    plt.savefig(png_bytes, format = "png", bbox_inches='tight')
    png_bytes.seek(0)
    
    if dev_mode:
        plt.savefig(f"stocks_{'_'.join(stocks_df.columns)}.png", format = "png", bbox_inches='tight')

    plt.close(fig)
    del fig
    
    return base64.b64encode(png_bytes.read()).decode()


def get_stocks_plot(tickers, section_frequency="monthly", dev_mode=False):
    """Get on stocks data for the issue.
    
    ARGUMENTS
    tickers (list of str): The abbreviation (ticker) of each stock  
    section_frequency (str): How often we are reporting stocks in issue. Determines how far in the past to plot.
    dev_mode (bool): If we're in dev/debug, output the plots to local files too.

    RETURNS
    stocks_plot (base64): Image for a single plot of tickers
    """
    # Map how often we deliver this plot to how much historical data (context) to include in the graph
    if section_frequency == "monthly":
        history = "quarter"
    elif section_frequency in ["every_other_week"]:
        history = "month"
    elif section_frequency in ["daily", "weekdays", "weekly"]:
        history = "week"
    else:
        logging.warning(f"Unexpected section_frequency in get_stocks_plot(): {tickers}, {section_frequency}")
        return None
    
    stocks_df = research_stock_histories(tickers)
    return plot_stocks(stocks_df, history, dev_mode)
