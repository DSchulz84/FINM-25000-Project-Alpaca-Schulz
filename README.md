# FINM-25000-Project-Alpaca-Schulz
The goal of this project was to code and execute a trading system in Alpaca. More specifically, the goal was to develop a strategy based on technical indicators which could connect with and exacute trades on the Alpaca trading website and in a backtesting mode based on historical data. Attached is a functional streamlit application which contains these modes and has full ability to test and trade on 15 pre-selected but changable stock tickers. 

## Architectural description
API keys connect the code to the Alpaca website which allows for the downloading of 5 years of histoical data, and comprehensive backtesting and performance evaluation of the strategy on the chosen stock tickers. The live paper trading requests live stock values and metrics, inputs them into the trading system, and either exacutes or holds off on trades, with full visability of current portfolio standing on the streamlit application. Both pages can be altered by use of slider controls which can change both the specific strategy technical indicator values and the risk managment measurements. 

## Setup instructions
Initialize API keys, chosen stock tickers, and specific strategy parameters in the .env file, and install the required bash packages. Save files for st_app.py, 1_Backtest_py, and 2_Live_Trade_py, and run the app through streamlit.

## Detailed strategy and risk description
The buy signal relies on 3 technical indicators: a SMA, which is the average price of a stock over some period of time, a MACD histogram, which measures the difference between two EMAs and a smoothed moving average, and the RSI, which is a momentum indicator which measures the extent to which a stock is overbought or underbought. Three market signals must be true in order for a buy to be executed. First, the current price/close must be greater than the current SMA 200, which itself must be greater than the SMA 200 from 20 days ago. Second, the MACD histogram must be less than zero, but greater than yesterday's MACD histogram, which in turn must be greater than the day before yesterday’s histogram. Finally, the RSI-14 must be greater than 60. 


The intention for the combination of these three market signals is to invest in historically stable stocks which have recently undergone a drop in price which the strategy decides is not a future indicator of the success of the stock. The SMA usage is meant to filter for stocks which have some amount of longer term stability as well as a reasonable current trend (SMA 200 increasing). The MACD histogram expands on this selection, filtering for stocks which specifically have had rough recent trading periods (MACD<0), but have seemingly already bottomed out (MACD rising over a few days) and are due for recovery. The RSI-14 eliminates all stocks which fit the first two criteria but are overbought, preventing the strategy from taking up positions in stocks due for pullback or buying at the top.

  
Although the only technical indicator used by the sell signal is the ATR, a measure of the stock’s recent volatility, an additional layer of complexity is added with the use of a time decay, and the addition of secondary conditions to the core sell signal. The formula for the core sell signal is stop_price=highest_close-((3-0.5t)*initial_ATR_14), where t is the number of days the position has been held. If the stock ever hits its stop price, the sell signal is sent. The idea behind this formula is that the willingness of the strategy to sell the position is proportional to the length of time the position has been held - the longer the stock has been sitting in the portfolio, the more eager the formula is to sell it. Secondarily, if the stock purchased is stagnant or fails to meaningfully trend for a period of 60 days, the sell signal is hit as well. Finally, in the case of successful stocks, if the stock price ever hits the value entry_price+3.5*initial_ATR_14, then both the time decay condition and the 60 day condition are removed, and instead the stock is held indefinitely until current_close<highest_close-2*initial_ATR_14, thereby locking the sell signal into a more rigid trailing stop. 

	
The purpose of the time decay sell signal is to prevent the strategy from purchasing stock only to dump them after early losses. Since the buy signal is influenced by longer term market signals, it makes conceptual sense to reduce the impact of recent events on the strategies sell signal decision making. By forcing the strategy to hold onto the position early, the longer term uptrends the buy signal is trying to identify are more frequently realized. The successful stock sell signal was a later addition to the strategy, as money was often lost due to the strategy unfairly punishing quality stocks with the combination of the time decay and 60 day window. This addition retains successful stocks within the portfolio, riding their momentum out until they hit closer to their peak value before selling. 

	
The risk management measures are simple but valuable. The volume of any one stock bought that satisfies the buy signals is proportional to the stock’s volatility: fewer shares of a more volatile stock are purchased than a more stable stock. There is also a pair of limits on total exposure. No one trade can invest more than 25% of the total portfolio equity, and no trade is allowed to cause a balance deficit by investing more than the liquid cash at the strategy's disposal. .

## Example usage

<img width="2868" height="1532" alt="image" src="https://github.com/user-attachments/assets/5ac52b1f-df30-4832-8897-b4cd092ab483" />


<img width="2912" height="1426" alt="image" src="https://github.com/user-attachments/assets/c3ef315e-4a29-4ace-8aac-9e582603d9da" />


```bash
pip install alpaca-py numpy pandas matplotlib backtesting python-dotenv streamlit
