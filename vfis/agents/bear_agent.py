"""
Bear Agent for VFIS - Analyzes risk and downside signals from stored data.

STRICT RULES:
- LLMs must NEVER generate financial numbers
- All facts must come from PostgreSQL
- Every claim must cite: table name, timestamp, source
- Only risk/downside signals (weak financials, negative sentiment, adverse technicals)
- Output must be structured, not narrative
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import date
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage

from vfis.tools.postgres_dal import VFISDataAccess, DataStatus
from vfis.tools.llm_factory import create_azure_openai_llm
from tradingagents.database.audit import log_data_access

logger = logging.getLogger(__name__)


class BearAgent:
    """
    Agent that analyzes ONLY risk and downside signals from stored financial data.
    
    CRITICAL: All financial numbers come from PostgreSQL. LLM only reasons about existing data.
    """
    
    def __init__(self, llm_model: Optional[str] = None):
        """
        Initialize Bear Agent.
        
        Args:
            llm_model: LLM model name (ignored for Azure OpenAI, deployment name comes from env)
        """
        self.llm = create_azure_openai_llm(temperature=0)
        self.agent_name = "BearAgent"
    
    def analyze_risk_signals(
        self,
        ticker: str,
        user_query: str = "Analyze risk signals"
    ) -> Dict[str, Any]:
        """
        Analyze risk and downside signals for a ticker from stored data.
        
        Returns structured output with citations.
        
        Args:
            ticker: Company ticker symbol
            user_query: Original user query for audit logging
            
        Returns:
            Dictionary with risk signals, each with citations
        """
        # Retrieve all available data
        signals = {
            'ticker': ticker,
            'analysis_date': date.today().isoformat(),
            'risk_signals': [],
            'data_sources': [],
            'warnings': [],
            'citations': []
        }
        
        try:
            # 1. Get fundamental data (quarterly financials)
            # Note: get_quarterly_financials returns (data, DataStatus) tuple
            balance_data, balance_status = VFISDataAccess.get_quarterly_financials(
                ticker=ticker,
                statement_type='balance_sheet',
                agent_name=self.agent_name,
                user_query=user_query
            )
            
            income_data, income_status = VFISDataAccess.get_quarterly_financials(
                ticker=ticker,
                statement_type='income_statement',
                agent_name=self.agent_name,
                user_query=user_query
            )
            
            cashflow_data, cashflow_status = VFISDataAccess.get_quarterly_financials(
                ticker=ticker,
                statement_type='cashflow_statement',
                agent_name=self.agent_name,
                user_query=user_query
            )
            
            # Extract staleness from data if available
            balance_stale = balance_data.get('days_old') if balance_data else None
            income_stale = income_data.get('days_old') if income_data else None
            cashflow_stale = cashflow_data.get('days_old') if cashflow_data else None
            
            # 2. Get negative sentiment data
            sentiment_data = self._get_negative_sentiment(ticker, user_query)
            
            # 3. Get adverse technical indicators
            technical_data = self._get_adverse_technicals(ticker, user_query)
            
            # 4. Analyze weaknesses (declining fundamentals, high debt, negative cash flow)
            fundamental_signals = self._analyze_fundamental_weaknesses(
                balance_data, income_data, cashflow_data,
                balance_status, income_status, cashflow_status
            )
            
            signals['risk_signals'].extend(fundamental_signals)
            signals['risk_signals'].extend(sentiment_data.get('signals', []))
            signals['risk_signals'].extend(technical_data.get('signals', []))
            
            # Collect data sources
            if balance_status == DataStatus.SUCCESS:
                signals['data_sources'].append({
                    'table': 'balance_sheet',
                    'status': 'available',
                    'staleness': balance_stale or None
                })
            if income_status == DataStatus.SUCCESS:
                signals['data_sources'].append({
                    'table': 'income_statement',
                    'status': 'available',
                    'staleness': income_stale or None
                })
            if cashflow_status == DataStatus.SUCCESS:
                signals['data_sources'].append({
                    'table': 'cashflow_statement',
                    'status': 'available',
                    'staleness': cashflow_stale or None
                })
            
            # Add warnings for missing/stale data
            if balance_status != DataStatus.SUCCESS:
                signals['warnings'].append(f"Balance sheet data unavailable or stale for {ticker}")
            if income_status != DataStatus.SUCCESS:
                signals['warnings'].append(f"Income statement data unavailable or stale for {ticker}")
            if cashflow_status != DataStatus.SUCCESS:
                signals['warnings'].append(f"Cash flow data unavailable or stale for {ticker}")
            
            # 5. Format structured output using LLM (reasoning only, no number generation)
            structured_output = self._format_structured_signals(signals)
            
            return structured_output
        
        except Exception as e:
            logger.error(f"BearAgent analysis failed for {ticker}: {e}", exc_info=True)
            log_data_access(
                event_type='agent_error',
                entity_type='bear_analysis',
                entity_id=None,
                details={'ticker': ticker, 'error': str(e)},
                user_id=self.agent_name
            )
            return {
                'ticker': ticker,
                'analysis_date': date.today().isoformat(),
                'risk_signals': [],
                'warnings': [f"Analysis failed: {str(e)}"],
                'data_sources': [],
                'citations': []
            }
    
    def _get_negative_sentiment(self, ticker: str, user_query: str) -> Dict[str, Any]:
        """Get negative sentiment signals from news table."""
        signals = {'signals': [], 'citations': []}
        
        try:
            from tradingagents.database.connection import get_db_connection
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check if news table exists
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'news'
                        );
                    """)
                    if not cur.fetchone()[0]:
                        return signals
                    
                    # Get recent negative sentiment news
                    cur.execute("""
                        SELECT n.headline, n.sentiment_score, n.sentiment_label, 
                               n.published_at, n.source_name, n.url
                        FROM news n
                        JOIN companies c ON n.company_id = c.id
                        WHERE c.ticker_symbol = %s
                        AND n.sentiment_label = 'negative'
                        AND n.sentiment_score < -0.1
                        ORDER BY n.published_at DESC
                        LIMIT 10
                    """, (ticker.upper(),))
                    
                    rows = cur.fetchall()
                    for row in rows:
                        headline, score, label, pub_date, source, url = row
                        signals['signals'].append({
                            'type': 'negative_sentiment',
                            'description': f"Negative news: {headline[:100]}",
                            'value': float(score) if score else None,
                            'table': 'news',
                            'timestamp': pub_date.isoformat() if pub_date else None,
                            'source': source or 'unknown'
                        })
                        signals['citations'].append({
                            'table': 'news',
                            'timestamp': pub_date.isoformat() if pub_date else None,
                            'source': source or 'unknown',
                            'url': url
                        })
        except Exception as e:
            logger.warning(f"Failed to get sentiment data for {ticker}: {e}")
        
        return signals
    
    def _get_adverse_technicals(self, ticker: str, user_query: str) -> Dict[str, Any]:
        """Get adverse technical indicator signals."""
        signals = {'signals': [], 'citations': []}
        
        try:
            from tradingagents.database.connection import get_db_connection
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check if technical_indicators table exists
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'technical_indicators'
                        );
                    """)
                    if not cur.fetchone()[0]:
                        return signals
                    
                    # Get recent technical indicators that suggest bearishness
                    # RSI > 70 (overbought), MACD negative, price below SMA
                    cur.execute("""
                        SELECT ti.indicator_name, ti.indicator_value, ti.calculated_date, ti.source
                        FROM technical_indicators ti
                        JOIN companies c ON ti.company_id = c.id
                        WHERE c.ticker_symbol = %s
                        AND ti.calculated_date >= CURRENT_DATE - INTERVAL '30 days'
                        AND (
                            (ti.indicator_name = 'rsi' AND ti.indicator_value > 70)
                            OR (ti.indicator_name = 'macd' AND ti.indicator_value < 0)
                            OR (ti.indicator_name LIKE 'bb_%' AND ti.indicator_value IS NOT NULL)
                        )
                        ORDER BY ti.calculated_date DESC, ti.indicator_name
                        LIMIT 20
                    """, (ticker.upper(),))
                    
                    rows = cur.fetchall()
                    for row in rows:
                        indicator_name, value, calc_date, source = row
                        signals['signals'].append({
                            'type': 'adverse_technical',
                            'description': f"{indicator_name.upper()} shows adverse pattern",
                            'value': float(value) if value else None,
                            'table': 'technical_indicators',
                            'timestamp': calc_date.isoformat() if calc_date else None,
                            'source': source or 'computed'
                        })
                        signals['citations'].append({
                            'table': 'technical_indicators',
                            'timestamp': calc_date.isoformat() if calc_date else None,
                            'source': source or 'computed',
                            'indicator': indicator_name
                        })
        except Exception as e:
            logger.warning(f"Failed to get technical indicators for {ticker}: {e}")
        
        return signals
    
    def _analyze_fundamental_weaknesses(
        self,
        balance_data: Dict,
        income_data: Dict,
        cashflow_data: Dict,
        balance_status: DataStatus,
        income_status: DataStatus,
        cashflow_status: DataStatus
    ) -> List[Dict[str, Any]]:
        """
        Analyze fundamental data for weaknesses and risks.
        
        CRITICAL: Only analyzes existing data. Does not generate numbers.
        """
        signals = []
        
        # Check for negative revenue or declining trends
        if income_status == DataStatus.SUCCESS and income_data:
            latest_quarter = income_data.get('latest_quarter')
            if latest_quarter:
                net_income = latest_quarter.get('Net Income') or latest_quarter.get('Profit After Tax')
                if net_income and float(net_income) < 0:
                    signals.append({
                        'type': 'fundamental_weakness',
                        'description': 'Negative net income in latest quarter',
                        'value': float(net_income),
                        'table': 'income_statement',
                        'timestamp': latest_quarter.get('as_of_date'),
                        'source': latest_quarter.get('source', 'unknown'),
                        'metric': 'Net Income'
                    })
        
        # Check for negative cash flow
        if cashflow_status == DataStatus.SUCCESS and cashflow_data:
            latest_quarter = cashflow_data.get('latest_quarter')
            if latest_quarter:
                operating_cf = latest_quarter.get('Operating Cash Flow') or latest_quarter.get('Cash from Operations')
                if operating_cf and float(operating_cf) < 0:
                    signals.append({
                        'type': 'fundamental_weakness',
                        'description': 'Negative operating cash flow',
                        'value': float(operating_cf),
                        'table': 'cashflow_statement',
                        'timestamp': latest_quarter.get('as_of_date'),
                        'source': latest_quarter.get('source', 'unknown'),
                        'metric': 'Operating Cash Flow'
                    })
        
        # Check for high debt-to-equity (if equity is negative or very small)
        if balance_status == DataStatus.SUCCESS and balance_data:
            latest_quarter = balance_data.get('latest_quarter')
            if latest_quarter:
                total_liabilities = latest_quarter.get('Total Liabilities')
                total_assets = latest_quarter.get('Total Assets')
                if total_liabilities and total_assets:
                    equity = float(total_assets) - float(total_liabilities)
                    if equity < 0:
                        signals.append({
                            'type': 'fundamental_weakness',
                            'description': 'Negative shareholders equity',
                            'value': equity,
                            'table': 'balance_sheet',
                            'timestamp': latest_quarter.get('as_of_date'),
                            'source': latest_quarter.get('source', 'unknown'),
                            'metric': 'Shareholders Equity'
                        })
                    elif equity > 0 and float(total_liabilities) / equity > 2.0:
                        signals.append({
                            'type': 'fundamental_weakness',
                            'description': 'High debt-to-equity ratio',
                            'value': float(total_liabilities) / equity,
                            'table': 'balance_sheet',
                            'timestamp': latest_quarter.get('as_of_date'),
                            'source': latest_quarter.get('source', 'unknown'),
                            'metric': 'Debt-to-Equity'
                        })
        
        return signals
    
    def _format_structured_signals(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format signals into structured output using LLM for reasoning only.
        
        CRITICAL: LLM only structures existing data. Does not generate numbers.
        """
        system_prompt = """You are a Bear Agent that analyzes ONLY risk and downside signals from financial data.

STRICT RULES:
- You must NEVER generate or invent financial numbers
- All numbers must come from the provided data
- Every claim must include citation (table, timestamp, source)
- Output must be structured JSON, not narrative
- Only highlight risk and downside signals

Your output should be a structured summary of risk signals with clear citations."""

        human_prompt = f"""Analyze the following risk signals for ticker {signals['ticker']}:

Risk Signals Found: {len(signals['risk_signals'])}
Data Sources: {signals['data_sources']}
Warnings: {signals['warnings']}

For each risk signal, provide:
1. Signal type (fundamental/sentiment/technical)
2. Brief description
3. Citation (table, timestamp, source)

Format as structured JSON with these fields:
- summary: Brief overview of risk signals
- key_risks: List of top risk signals with citations
- data_quality: Status of underlying data

DO NOT generate any financial numbers. Only reference numbers from the provided data."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
            
            response = self.llm.invoke(messages)
            
            # Parse LLM response and merge with original signals data
            structured_output = {
                'ticker': signals['ticker'],
                'analysis_date': signals['analysis_date'],
                'risk_signals': signals['risk_signals'],
                'data_sources': signals['data_sources'],
                'warnings': signals['warnings'],
                'citations': signals.get('citations', []),
                'llm_summary': response.content,
                'agent_name': self.agent_name
            }
            
            return structured_output
        
        except Exception as e:
            logger.error(f"Failed to format structured signals: {e}")
            return signals

