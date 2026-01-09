"""
Deterministic technical indicators computation for VFIS.

STRICT RULES:
- All computations use data already stored in PostgreSQL
- No live market APIs
- No LLM-based calculations, sentiment guessing, or forecasting
- LLMs must NEVER generate financial numbers
- Calculations must be reproducible
- No subjective thresholds
- No forecasting

This module computes technical indicators from stored OHLC data.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np

from tradingagents.database.connection import get_db_connection

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """
    Compute technical indicators deterministically from stored OHLC data.
    
    CRITICAL: All calculations are deterministic and reproducible.
    No LLM usage, no forecasting, no subjective interpretations.
    """
    
    def __init__(self, ticker: str):
        """
        Initialize technical indicators computer.
        
        Args:
            ticker: Company ticker symbol (dynamically provided)
        """
        self.ticker = ticker.upper()
    
    def get_ohlc_data(
        self,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Retrieve OHLC data from PostgreSQL.
        
        Note: This assumes an ohlc_data table exists. If not, this is a placeholder
        for the actual table structure based on your schema.
        
        Args:
            start_date: Start date for data retrieval
            end_date: End date for data retrieval
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        # Note: This is a placeholder. You'll need to implement based on your actual
        # OHLC data table structure. For now, returning empty DataFrame structure.
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if ohlc_data table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'ohlc_data'
                    );
                """)
                table_exists = cur.fetchone()[0]
                
                if not table_exists:
                    logger.warning("ohlc_data table does not exist. Cannot compute indicators.")
                    return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                
                # Retrieve OHLC data
                cur.execute("""
                    SELECT trade_date, open_price, high_price, low_price, close_price, volume
                    FROM ohlc_data
                    WHERE ticker = %s 
                    AND trade_date >= %s 
                    AND trade_date <= %s
                    ORDER BY trade_date ASC
                """, (self.ticker, start_date, end_date))
                
                rows = cur.fetchall()
                
                if not rows:
                    logger.warning(f"No OHLC data found for {self.ticker} between {start_date} and {end_date}")
                    return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                
                # Convert to DataFrame
                df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                return df
    
    def compute_sma(self, prices: pd.Series, window: int) -> pd.Series:
        """
        Compute Simple Moving Average (SMA).
        
        Formula: SMA = sum(prices) / window
        
        Args:
            prices: Series of price data (typically close prices)
            window: Window size (e.g., 20, 50, 200)
            
        Returns:
            Series of SMA values
        """
        return prices.rolling(window=window).mean()
    
    def compute_ema(self, prices: pd.Series, window: int) -> pd.Series:
        """
        Compute Exponential Moving Average (EMA).
        
        Formula: EMA = price * multiplier + EMA_prev * (1 - multiplier)
        where multiplier = 2 / (window + 1)
        
        Args:
            prices: Series of price data
            window: Window size
            
        Returns:
            Series of EMA values
        """
        return prices.ewm(span=window, adjust=False).mean()
    
    def compute_rsi(self, prices: pd.Series, window: int = 14) -> pd.Series:
        """
        Compute Relative Strength Index (RSI).
        
        Formula:
        - delta = price changes
        - gain = positive changes, loss = negative changes (as positive)
        - avg_gain = EMA of gains
        - avg_loss = EMA of losses
        - RS = avg_gain / avg_loss
        - RSI = 100 - (100 / (1 + RS))
        
        Args:
            prices: Series of price data
            window: Window size (default 14)
            
        Returns:
            Series of RSI values (0-100)
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def compute_macd(
        self,
        prices: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, pd.Series]:
        """
        Compute MACD (Moving Average Convergence Divergence).
        
        Formula:
        - MACD_line = EMA(fast) - EMA(slow)
        - Signal_line = EMA(MACD_line, signal_period)
        - Histogram = MACD_line - Signal_line
        
        Args:
            prices: Series of price data
            fast: Fast EMA period (default 12)
            slow: Slow EMA period (default 26)
            signal: Signal line period (default 9)
            
        Returns:
            Dictionary with 'macd', 'signal', 'histogram' Series
        """
        ema_fast = self.compute_ema(prices, fast)
        ema_slow = self.compute_ema(prices, slow)
        macd_line = ema_fast - ema_slow
        signal_line = self.compute_ema(macd_line, signal)
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def compute_bollinger_bands(
        self,
        prices: pd.Series,
        window: int = 20,
        num_std: float = 2.0
    ) -> Dict[str, pd.Series]:
        """
        Compute Bollinger Bands.
        
        Formula:
        - Middle = SMA(prices, window)
        - Upper = Middle + (std * num_std)
        - Lower = Middle - (std * num_std)
        
        Args:
            prices: Series of price data
            window: Window size (default 20)
            num_std: Number of standard deviations (default 2.0)
            
        Returns:
            Dictionary with 'upper', 'middle', 'lower' Series
        """
        middle = self.compute_sma(prices, window)
        std = prices.rolling(window=window).std()
        upper = middle + (std * num_std)
        lower = middle - (std * num_std)
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }
    
    def compute_stochastic(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_window: int = 14,
        d_window: int = 3
    ) -> Dict[str, pd.Series]:
        """
        Compute Stochastic Oscillator.
        
        Formula:
        - %K = 100 * (close - low_min) / (high_max - low_min)
        - %D = SMA(%K, d_window)
        
        Args:
            high: Series of high prices
            low: Series of low prices
            close: Series of close prices
            k_window: %K window (default 14)
            d_window: %D window (default 3)
            
        Returns:
            Dictionary with 'k', 'd' Series
        """
        low_min = low.rolling(window=k_window).min()
        high_max = high.rolling(window=k_window).max()
        
        k_percent = 100 * (close - low_min) / (high_max - low_min)
        d_percent = self.compute_sma(k_percent, d_window)
        
        return {
            'k': k_percent,
            'd': d_percent
        }
    
    def compute_all_indicators(
        self,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Compute all technical indicators for the given date range.
        
        Returns:
            DataFrame with all indicator values
        """
        # Get OHLC data
        ohlc_df = self.get_ohlc_data(start_date, end_date)
        
        if ohlc_df.empty:
            logger.warning(f"No OHLC data available for {self.ticker}")
            return pd.DataFrame()
        
        close = ohlc_df['close']
        high = ohlc_df['high']
        low = ohlc_df['low']
        
        # Initialize result DataFrame
        result_df = pd.DataFrame(index=ohlc_df.index)
        result_df['close'] = close
        
        # Compute indicators
        result_df['sma_20'] = self.compute_sma(close, 20)
        result_df['sma_50'] = self.compute_sma(close, 50)
        result_df['sma_200'] = self.compute_sma(close, 200)
        
        result_df['ema_12'] = self.compute_ema(close, 12)
        result_df['ema_26'] = self.compute_ema(close, 26)
        
        result_df['rsi'] = self.compute_rsi(close, 14)
        
        macd = self.compute_macd(close)
        result_df['macd'] = macd['macd']
        result_df['macd_signal'] = macd['signal']
        result_df['macd_histogram'] = macd['histogram']
        
        bb = self.compute_bollinger_bands(close)
        result_df['bb_upper'] = bb['upper']
        result_df['bb_middle'] = bb['middle']
        result_df['bb_lower'] = bb['lower']
        
        stoch = self.compute_stochastic(high, low, close)
        result_df['stoch_k'] = stoch['k']
        result_df['stoch_d'] = stoch['d']
        
        return result_df


def store_technical_indicators(
    ticker: str,
    indicator_name: str,
    indicator_values: pd.Series,
    source: str = 'computed',
    calculated_date: Optional[date] = None
) -> int:
    """
    Store computed technical indicators in PostgreSQL.
    
    CRITICAL: All values are deterministically computed from stored data.
    
    Args:
        ticker: Company ticker symbol
        indicator_name: Name of indicator (e.g., 'SMA_20', 'RSI')
        indicator_values: Series with date index and indicator values
        source: Source of data ('computed' for calculated indicators)
        calculated_date: Date when calculated (defaults to today)
        
    Returns:
        Number of records inserted
    """
    from tradingagents.database.connection import get_db_connection
    
    # Get company ID
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id FROM companies WHERE ticker_symbol = %s AND is_active = TRUE
            """, (ticker.upper(),))
            result = cur.fetchone()
            if not result:
                logger.error(f"Company {ticker} not found in database")
                return 0
            company_id = result[0]
    
    # Get company ID
    company = FinancialDataAccess.get_company_by_ticker(ticker)
    if not company:
        logger.error(f"Company {ticker} not found in database")
        return 0
    
    
    if calculated_date is None:
        calculated_date = date.today()
    
    records_inserted = 0
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for calc_date, value in indicator_values.items():
                # Skip NaN values
                if pd.isna(value):
                    continue
                
                try:
                    cur.execute("""
                        INSERT INTO technical_indicators 
                        (company_id, indicator_name, indicator_value, calculated_date, source)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (company_id, indicator_name, calculated_date) DO UPDATE
                        SET indicator_value = EXCLUDED.indicator_value,
                            source = EXCLUDED.source,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        company_id,
                        indicator_name,
                        float(value),
                        calc_date.date() if isinstance(calc_date, pd.Timestamp) else calculated_date,
                        source
                    ))
                    records_inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to insert indicator {indicator_name} for {calc_date}: {e}")
                    continue
            
            conn.commit()
    
    logger.info(f"Stored {records_inserted} {indicator_name} values for {ticker}")
    return records_inserted

