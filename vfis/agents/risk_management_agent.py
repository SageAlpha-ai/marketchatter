"""
Risk Management Agent for VFIS - Classifies risk using deterministic rules.

STRICT RULES:
- Reads precomputed risk metrics from PostgreSQL
- Uses deterministic rules to classify risk (HIGH, MODERATE, LOW)
- No calculations inside LLM
- No Alpha/Beta computation here
- Only explanation of existing metrics
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import date, timedelta
from enum import Enum

from vfis.tools.postgres_dal import VFISDataAccess, DataStatus
from tradingagents.database.connection import get_db_connection
from tradingagents.database.audit import log_data_access

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk classification levels."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class RiskManagementAgent:
    """
    Agent that classifies risk using deterministic rules on stored data.
    
    CRITICAL: All risk metrics come from PostgreSQL. No calculations in LLM.
    """
    
    def __init__(self):
        """Initialize Risk Management Agent."""
        self.agent_name = "RiskManagementAgent"
    
    def classify_risk(
        self,
        ticker: str,
        user_query: str = "Classify risk"
    ) -> Dict[str, Any]:
        """
        Classify risk level using deterministic rules on stored data.
        
        Args:
            ticker: Company ticker symbol
            user_query: Original user query for audit logging
            
        Returns:
            Dictionary with risk classification and explanations
        """
        risk_assessment = {
            'ticker': ticker,
            'analysis_date': date.today().isoformat(),
            'risk_level': None,
            'risk_factors': [],
            'data_sources': [],
            'warnings': [],
            'explanation': ''
        }
        
        try:
            # Collect risk factors from various data sources
            risk_factors = []
            
            # 1. Financial health factors
            financial_risk = self._assess_financial_risk(ticker, user_query)
            risk_factors.extend(financial_risk.get('factors', []))
            if financial_risk.get('data_source'):
                risk_assessment['data_sources'].append(financial_risk['data_source'])
            
            # 2. Sentiment risk factors
            sentiment_risk = self._assess_sentiment_risk(ticker, user_query)
            risk_factors.extend(sentiment_risk.get('factors', []))
            if sentiment_risk.get('data_source'):
                risk_assessment['data_sources'].append(sentiment_risk['data_source'])
            
            # 3. Technical risk factors
            technical_risk = self._assess_technical_risk(ticker, user_query)
            risk_factors.extend(technical_risk.get('factors', []))
            if technical_risk.get('data_source'):
                risk_assessment['data_sources'].append(technical_risk['data_source'])
            
            # 4. Data staleness risk
            staleness_risk = self._assess_data_staleness(ticker, user_query)
            risk_factors.extend(staleness_risk.get('factors', []))
            
            risk_assessment['risk_factors'] = risk_factors
            risk_assessment['warnings'].extend(financial_risk.get('warnings', []))
            risk_assessment['warnings'].extend(sentiment_risk.get('warnings', []))
            risk_assessment['warnings'].extend(technical_risk.get('warnings', []))
            risk_assessment['warnings'].extend(staleness_risk.get('warnings', []))
            
            # 5. Deterministic risk classification
            risk_level = self._classify_risk_level(risk_factors)
            risk_assessment['risk_level'] = risk_level.value
            
            # 6. Generate explanation
            risk_assessment['explanation'] = self._generate_explanation(
                risk_level, risk_factors, risk_assessment['warnings']
            )
            
            # Log risk classification
            log_data_access(
                event_type='risk_classification',
                entity_type='ticker',
                entity_id=None,
                details={
                    'ticker': ticker,
                    'risk_level': risk_level.value,
                    'risk_factors_count': len(risk_factors)
                },
                user_id=self.agent_name
            )
            
            return risk_assessment
        
        except Exception as e:
            logger.error(f"Risk classification failed for {ticker}: {e}", exc_info=True)
            log_data_access(
                event_type='risk_classification_error',
                entity_type='ticker',
                entity_id=None,
                details={'ticker': ticker, 'error': str(e)},
                user_id=self.agent_name
            )
            return {
                'ticker': ticker,
                'analysis_date': date.today().isoformat(),
                'risk_level': 'UNKNOWN',
                'error': str(e),
                'risk_factors': [],
                'warnings': [f"Risk classification failed: {str(e)}"]
            }
    
    def _assess_financial_risk(self, ticker: str, user_query: str) -> Dict[str, Any]:
        """Assess financial risk factors from balance sheet and income statement."""
        factors = []
        warnings = []
        
        try:
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
            
            # Extract staleness from data if available
            balance_stale = balance_data.get('days_old') if balance_data else None
            income_stale = income_data.get('days_old') if income_data else None
            
            if balance_status != DataStatus.SUCCESS:
                warnings.append("Balance sheet data unavailable for risk assessment")
                return {'factors': factors, 'warnings': warnings}
            
            if income_status != DataStatus.SUCCESS:
                warnings.append("Income statement data unavailable for risk assessment")
                return {'factors': factors, 'warnings': warnings}
            
            # Check for negative equity (HIGH risk)
            if balance_data and balance_data.get('latest_quarter'):
                latest = balance_data['latest_quarter']
                total_assets = latest.get('Total Assets')
                total_liabilities = latest.get('Total Liabilities')
                
                if total_assets and total_liabilities:
                    equity = float(total_assets) - float(total_liabilities)
                    if equity < 0:
                        factors.append({
                            'type': 'financial',
                            'severity': 'HIGH',
                            'description': 'Negative shareholders equity',
                            'value': equity,
                            'table': 'balance_sheet',
                            'timestamp': latest.get('as_of_date'),
                            'source': latest.get('source', 'unknown')
                        })
                    elif equity > 0 and float(total_liabilities) / equity > 3.0:
                        factors.append({
                            'type': 'financial',
                            'severity': 'HIGH',
                            'description': 'Very high debt-to-equity ratio',
                            'value': float(total_liabilities) / equity,
                            'table': 'balance_sheet',
                            'timestamp': latest.get('as_of_date'),
                            'source': latest.get('source', 'unknown')
                        })
            
            # Check for negative net income (MODERATE risk)
            if income_data and income_data.get('latest_quarter'):
                latest = income_data['latest_quarter']
                net_income = latest.get('Net Income') or latest.get('Profit After Tax')
                
                if net_income and float(net_income) < 0:
                    factors.append({
                        'type': 'financial',
                        'severity': 'MODERATE',
                        'description': 'Negative net income',
                        'value': float(net_income),
                        'table': 'income_statement',
                        'timestamp': latest.get('as_of_date'),
                        'source': latest.get('source', 'unknown')
                    })
            
            if balance_stale and balance_stale > 120:
                warnings.append(f"Balance sheet data may be stale: {balance_stale} days old")
            if income_stale and income_stale > 120:
                warnings.append(f"Income statement data may be stale: {income_stale} days old")
            
            return {
                'factors': factors,
                'warnings': warnings,
                'data_source': 'balance_sheet, income_statement'
            }
        
        except Exception as e:
            logger.warning(f"Failed to assess financial risk for {ticker}: {e}")
            return {'factors': factors, 'warnings': [f"Financial risk assessment failed: {str(e)}"]}
    
    def _assess_sentiment_risk(self, ticker: str, user_query: str) -> Dict[str, Any]:
        """Assess sentiment risk from news table."""
        factors = []
        warnings = []
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'news'
                        );
                    """)
                    if not cur.fetchone()[0]:
                        warnings.append("News table does not exist")
                        return {'factors': factors, 'warnings': warnings}
                    
                    # Count recent negative sentiment articles
                    cur.execute("""
                        SELECT COUNT(*), AVG(n.sentiment_score)
                        FROM news n
                        JOIN companies c ON n.company_id = c.id
                        WHERE c.ticker_symbol = %s
                        AND n.published_at >= CURRENT_DATE - INTERVAL '30 days'
                        AND n.sentiment_label = 'negative'
                    """, (ticker.upper(),))
                    
                    result = cur.fetchone()
                    negative_count = result[0] if result[0] else 0
                    avg_sentiment = float(result[1]) if result[1] else 0
                    
                    if negative_count >= 5:
                        factors.append({
                            'type': 'sentiment',
                            'severity': 'MODERATE',
                            'description': f'Multiple negative news articles in past 30 days ({negative_count})',
                            'value': negative_count,
                            'table': 'news',
                            'timestamp': date.today().isoformat(),
                            'source': 'news'
                        })
                    
                    if avg_sentiment < -0.3:
                        factors.append({
                            'type': 'sentiment',
                            'severity': 'MODERATE',
                            'description': 'Very negative average sentiment score',
                            'value': avg_sentiment,
                            'table': 'news',
                            'timestamp': date.today().isoformat(),
                            'source': 'news'
                        })
            
            return {
                'factors': factors,
                'warnings': warnings,
                'data_source': 'news'
            }
        
        except Exception as e:
            logger.warning(f"Failed to assess sentiment risk for {ticker}: {e}")
            return {'factors': factors, 'warnings': [f"Sentiment risk assessment failed: {str(e)}"]}
    
    def _assess_technical_risk(self, ticker: str, user_query: str) -> Dict[str, Any]:
        """Assess technical risk from technical indicators."""
        factors = []
        warnings = []
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'technical_indicators'
                        );
                    """)
                    if not cur.fetchone()[0]:
                        warnings.append("Technical indicators table does not exist")
                        return {'factors': factors, 'warnings': warnings}
                    
                    # Check for overbought conditions (RSI > 70)
                    cur.execute("""
                        SELECT ti.indicator_value, ti.calculated_date
                        FROM technical_indicators ti
                        JOIN companies c ON ti.company_id = c.id
                        WHERE c.ticker_symbol = %s
                        AND ti.indicator_name = 'rsi'
                        AND ti.calculated_date >= CURRENT_DATE - INTERVAL '7 days'
                        ORDER BY ti.calculated_date DESC
                        LIMIT 1
                    """, (ticker.upper(),))
                    
                    result = cur.fetchone()
                    if result and result[0]:
                        rsi_value = float(result[0])
                        if rsi_value > 70:
                            factors.append({
                                'type': 'technical',
                                'severity': 'MODERATE',
                                'description': 'RSI indicates overbought condition',
                                'value': rsi_value,
                                'table': 'technical_indicators',
                                'timestamp': result[1].isoformat() if result[1] else None,
                                'source': 'computed'
                            })
            
            return {
                'factors': factors,
                'warnings': warnings,
                'data_source': 'technical_indicators'
            }
        
        except Exception as e:
            logger.warning(f"Failed to assess technical risk for {ticker}: {e}")
            return {'factors': factors, 'warnings': [f"Technical risk assessment failed: {str(e)}"]}
    
    def _assess_data_staleness(self, ticker: str, user_query: str) -> Dict[str, Any]:
        """Assess risk from data staleness."""
        factors = []
        warnings = []
        
        try:
            # Check staleness of financial data
            # Note: get_quarterly_financials returns (data, DataStatus) tuple
            balance_data, balance_status = VFISDataAccess.get_quarterly_financials(
                ticker=ticker,
                statement_type='balance_sheet',
                agent_name=self.agent_name,
                user_query=user_query
            )
            
            # Extract days_old from data to check staleness
            balance_stale = balance_data.get('days_old') if balance_data else None
            
            if balance_stale and balance_stale > 120:
                factors.append({
                    'type': 'data_quality',
                    'severity': 'MODERATE',
                    'description': f'Financial data is {balance_stale} days old',
                    'value': balance_stale,
                    'table': 'balance_sheet',
                    'timestamp': None,
                    'source': 'unknown'
                })
                warnings.append(f"Balance sheet data is {balance_stale} days old")
            
            return {'factors': factors, 'warnings': warnings}
        
        except Exception as e:
            logger.warning(f"Failed to assess data staleness for {ticker}: {e}")
            return {'factors': factors, 'warnings': []}
    
    def _classify_risk_level(self, risk_factors: List[Dict[str, Any]]) -> RiskLevel:
        """
        Classify risk level using deterministic rules.
        
        Rules:
        - HIGH: Any HIGH severity factor
        - MODERATE: 2+ MODERATE factors or any MODERATE with data staleness
        - LOW: Otherwise
        """
        high_factors = [f for f in risk_factors if f.get('severity') == 'HIGH']
        moderate_factors = [f for f in risk_factors if f.get('severity') == 'MODERATE']
        
        if high_factors:
            return RiskLevel.HIGH
        elif len(moderate_factors) >= 2:
            return RiskLevel.MODERATE
        elif moderate_factors:
            return RiskLevel.MODERATE
        else:
            return RiskLevel.LOW
    
    def _generate_explanation(
        self,
        risk_level: RiskLevel,
        risk_factors: List[Dict[str, Any]],
        warnings: List[str]
    ) -> str:
        """Generate explanation of risk classification."""
        explanation_parts = [f"Risk Level: {risk_level.value}"]
        
        if risk_factors:
            explanation_parts.append(f"\nRisk Factors Identified: {len(risk_factors)}")
            for factor in risk_factors[:3]:  # Top 3 factors
                explanation_parts.append(
                    f"- {factor.get('type', 'unknown')}: {factor.get('description', 'N/A')} "
                    f"(severity: {factor.get('severity', 'unknown')})"
                )
        else:
            explanation_parts.append("\nNo significant risk factors identified.")
        
        if warnings:
            explanation_parts.append(f"\nData Quality Warnings: {len(warnings)}")
            for warning in warnings[:3]:
                explanation_parts.append(f"- {warning}")
        
        return "\n".join(explanation_parts)

