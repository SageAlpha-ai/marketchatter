"""
Final Output Assembly for VFIS - Assembles complete analysis response.

STRICT RULES:
- Include: Bull vs Bear summary, Risk classification, Subscriber suitability,
  Data sources and as-of dates
- If data is missing or stale: explicitly state limitation
- Do not infer or guess
"""

import logging
from typing import Dict, Any, Optional, List

from vfis.agents.debate_orchestrator import DebateOrchestrator
from vfis.agents.risk_management_agent import RiskManagementAgent
from vfis.tools.subscriber_matching import SubscriberMatcher, SubscriberRiskTolerance
from vfis.tools.postgres_dal import VFISDataAccess
from tradingagents.database.chatter_dal import get_recent_chatter  # Canonical DAL
from tradingagents.database.audit import log_data_access

logger = logging.getLogger(__name__)


class FinalOutputAssembly:
    """
    Assembles final structured output combining all analysis components.
    
    CRITICAL: All data from PostgreSQL with explicit limitations stated.
    """
    
    def __init__(self, llm_model: Optional[str] = None):
        """
        Initialize Final Output Assembly.
        
        Args:
            llm_model: LLM model name for debate agents
        """
        self.debate_orchestrator = DebateOrchestrator(llm_model=llm_model)
        self.risk_agent = RiskManagementAgent()
        self.subscriber_matcher = SubscriberMatcher()
        # NOTE: Using canonical chatter_dal instead of deprecated storage module
    
    def assemble_final_output(
        self,
        ticker: str,
        subscriber_risk_tolerance: Optional[SubscriberRiskTolerance] = None,
        user_query: str = "Complete analysis"
    ) -> Dict[str, Any]:
        """
        Assemble complete structured output for a ticker.
        
        Args:
            ticker: Company ticker symbol
            subscriber_risk_tolerance: Optional subscriber risk tolerance for matching
            user_query: Original user query
            
        Returns:
            Complete structured analysis output
        """
        try:
            # 1. Bull vs Bear Debate
            debate_output = self.debate_orchestrator.conduct_debate(
                ticker=ticker,
                user_query=user_query
            )
            
            # 2. Risk Classification
            risk_assessment = self.risk_agent.classify_risk(
                ticker=ticker,
                user_query=user_query
            )
            
            # 3. Market Chatter and Sentiment
            market_chatter_data = self._get_market_chatter_and_sentiment(ticker)
            
            # 4. Latest Financial Metrics
            latest_financial_metrics = self._get_latest_financial_metrics(ticker)
            
            # 5. Subscriber Matching for all risk levels
            subscriber_views = self._get_all_subscriber_views(ticker, user_query)
            
            # 6. Subscriber Matching (if subscriber tolerance provided)
            subscriber_match = None
            if subscriber_risk_tolerance:
                subscriber_match = self.subscriber_matcher.match_company_to_subscriber(
                    ticker=ticker,
                    subscriber_risk_tolerance=subscriber_risk_tolerance,
                    user_query=user_query
                )
            
            # 7. Assemble final output
            final_output = {
                'ticker': ticker,
                'analysis_date': debate_output.get('analysis_date'),
                'output_format': 'structured',
                'latest_financial_metrics': latest_financial_metrics,
                'market_chatter_summary': market_chatter_data.get('summary', ''),
                'sentiment_score': market_chatter_data.get('sentiment_score'),
                'sentiment_label': market_chatter_data.get('sentiment_label'),
                'bull_case': debate_output.get('bull_perspective', {}).get('summary', ''),
                'bear_case': debate_output.get('bear_perspective', {}).get('summary', ''),
                'risk_assessment': {
                    'overall_risk': risk_assessment.get('risk_level'),
                    'low_risk_subscriber_view': subscriber_views.get('low_risk', {}),
                    'moderate_risk_subscriber_view': subscriber_views.get('moderate_risk', {}),
                    'high_risk_subscriber_view': subscriber_views.get('high_risk', {})
                },
                'components': {
                    'bull_vs_bear_debate': {
                        'bull_signals_count': debate_output.get('bull_perspective', {}).get('positive_signals_count', 0),
                        'bear_signals_count': debate_output.get('bear_perspective', {}).get('risk_signals_count', 0),
                        'bull_summary': debate_output.get('bull_perspective', {}).get('summary', ''),
                        'bear_summary': debate_output.get('bear_perspective', {}).get('summary', ''),
                        'key_bull_signals': debate_output.get('bull_perspective', {}).get('key_signals', [])[:3],
                        'key_bear_signals': debate_output.get('bear_perspective', {}).get('key_risks', [])[:3]
                    },
                    'risk_classification': {
                        'risk_level': risk_assessment.get('risk_level'),
                        'risk_factors_count': len(risk_assessment.get('risk_factors', [])),
                        'explanation': risk_assessment.get('explanation', ''),
                        'key_risk_factors': risk_assessment.get('risk_factors', [])[:3]
                    },
                    'subscriber_suitability': subscriber_match if subscriber_match else {
                        'status': 'not_checked',
                        'reason': 'Subscriber risk tolerance not provided'
                    }
                },
                'data_sources': self._consolidate_data_sources(debate_output, risk_assessment),
                'data_quality': {
                    'warnings': self._consolidate_warnings(debate_output, risk_assessment),
                    'limitations': self._identify_limitations(debate_output, risk_assessment)
                },
                'citations': {
                    'bull_citations': debate_output.get('citations', {}).get('bull_citations', []),
                    'bear_citations': debate_output.get('citations', {}).get('bear_citations', []),
                    'risk_citations': risk_assessment.get('risk_factors', [])
                },
                'as_of_dates': self._extract_as_of_dates(debate_output, risk_assessment)
            }
            
            # Log final output assembly
            log_data_access(
                event_type='final_output_assembly',
                entity_type='ticker_analysis',
                entity_id=None,
                details={
                    'ticker': ticker,
                    'risk_level': risk_assessment.get('risk_level'),
                    'subscriber_matched': subscriber_match is not None and subscriber_match.get('is_match', False) if subscriber_match else False
                },
                user_id='FinalOutputAssembly'
            )
            
            return final_output
        
        except Exception as e:
            logger.error(f"Final output assembly failed for {ticker}: {e}", exc_info=True)
            log_data_access(
                event_type='final_output_assembly_error',
                entity_type='ticker_analysis',
                entity_id=None,
                details={'ticker': ticker, 'error': str(e)},
                user_id='FinalOutputAssembly'
            )
            return {
                'ticker': ticker,
                'error': str(e),
                'output_format': 'structured',
                'components': {},
                'data_quality': {
                    'warnings': [f"Output assembly failed: {str(e)}"],
                    'limitations': ['Unable to complete analysis due to error']
                }
            }
    
    def _consolidate_data_sources(
        self,
        debate_output: Dict[str, Any],
        risk_assessment: Dict[str, Any]
    ) -> List[str]:
        """Consolidate data sources from all components."""
        sources = set()
        
        # From debate output
        bull_sources = debate_output.get('bull_perspective', {}).get('data_sources', [])
        bear_sources = debate_output.get('bear_perspective', {}).get('data_sources', [])
        for source in bull_sources + bear_sources:
            if isinstance(source, dict):
                sources.add(source.get('table', 'unknown'))
            else:
                sources.add(str(source))
        
        # From risk assessment
        risk_sources = risk_assessment.get('data_sources', [])
        for source in risk_sources:
            if isinstance(source, dict):
                sources.add(source.get('table', 'unknown'))
            else:
                sources.add(str(source))
        
        return list(sources)
    
    def _consolidate_warnings(
        self,
        debate_output: Dict[str, Any],
        risk_assessment: Dict[str, Any]
    ) -> List[str]:
        """Consolidate warnings from all components."""
        warnings = set()
        
        # From debate output
        debate_warnings = debate_output.get('data_quality', {}).get('combined_warnings', [])
        warnings.update(debate_warnings)
        
        # From risk assessment
        risk_warnings = risk_assessment.get('warnings', [])
        warnings.update(risk_warnings)
        
        return list(warnings)
    
    def _identify_limitations(
        self,
        debate_output: Dict[str, Any],
        risk_assessment: Dict[str, Any]
    ) -> List[str]:
        """Identify data limitations explicitly."""
        limitations = []
        
        warnings = self._consolidate_warnings(debate_output, risk_assessment)
        
        if any('stale' in w.lower() for w in warnings):
            limitations.append("Some financial data may be stale. Latest available data used.")
        
        if any('unavailable' in w.lower() for w in warnings):
            limitations.append("Some data sources are unavailable. Analysis based on available data only.")
        
        if not debate_output.get('bull_perspective', {}).get('positive_signals_count', 0) and \
           not debate_output.get('bear_perspective', {}).get('risk_signals_count', 0):
            limitations.append("Insufficient data to generate meaningful signals. Analysis may be incomplete.")
        
        return limitations
    
    def _extract_as_of_dates(
        self,
        debate_output: Dict[str, Any],
        risk_assessment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract as-of dates from all data sources."""
        as_of_dates = {
            'earliest': None,
            'latest': None,
            'sources': []
        }
        
        # Extract from citations
        all_citations = []
        all_citations.extend(debate_output.get('citations', {}).get('bull_citations', []))
        all_citations.extend(debate_output.get('citations', {}).get('bear_citations', []))
        
        dates = []
        for citation in all_citations:
            if isinstance(citation, dict) and citation.get('timestamp'):
                dates.append(citation['timestamp'])
                as_of_dates['sources'].append({
                    'table': citation.get('table', 'unknown'),
                    'timestamp': citation['timestamp'],
                    'source': citation.get('source', 'unknown')
                })
        
        if dates:
            as_of_dates['earliest'] = min(dates)
            as_of_dates['latest'] = max(dates)
        
        return as_of_dates
    
    def _get_market_chatter_and_sentiment(self, ticker: str) -> Dict[str, Any]:
        """
        Retrieve market chatter and compute overall sentiment.
        
        Args:
            ticker: Company ticker symbol
            
        Returns:
            Dictionary with market chatter summary and sentiment data
        """
        try:
            # Get recent market chatter (last 30 days) - using canonical DAL
            # Returns standard DAL response: {"data": {...}, "status": str, "message": str}
            chatter_response = get_recent_chatter(ticker, days=30, limit=100)
            
            # Handle new dict contract
            if isinstance(chatter_response, dict):
                if chatter_response.get("status") == "error":
                    logger.warning(f"Market chatter error: {chatter_response.get('message')}")
                    return {
                        'summary': f'Unable to retrieve market chatter for {ticker}',
                        'sentiment_score': 0.0,
                        'sentiment_label': 'neutral',
                        'item_count': 0
                    }
                
                # Extract data from response
                data = chatter_response.get("data", chatter_response)
                chatter_items = data.get("items", [])
                sources = data.get("sources", {})
            else:
                # Legacy: direct list return
                chatter_items = chatter_response if isinstance(chatter_response, list) else []
                sources = {}
            
            if not chatter_items:
                return {
                    'summary': f'No market chatter found for {ticker} in the last 30 days.',
                    'sentiment_score': 0.0,
                    'sentiment_label': 'neutral',
                    'item_count': 0
                }
            
            # Compute overall sentiment from individual sentiment scores
            sentiment_scores = []
            for item in chatter_items:
                score = item.get('sentiment_score')
                if score is not None:
                    try:
                        sentiment_scores.append(float(score))
                    except (ValueError, TypeError):
                        pass
            
            if sentiment_scores:
                avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
                # Determine label
                if avg_sentiment > 0.2:
                    sentiment_label = 'bullish'
                elif avg_sentiment < -0.2:
                    sentiment_label = 'bearish'
                else:
                    sentiment_label = 'neutral'
            else:
                avg_sentiment = 0.0
                sentiment_label = 'neutral'
            
            # Build sources if not already provided
            if not sources:
                for item in chatter_items:
                    source = item.get('source', 'unknown')
                    sources[source] = sources.get(source, 0) + 1
            
            summary_parts = [f"Found {len(chatter_items)} market chatter items from {len(sources)} sources"]
            if sources:
                summary_parts.append(f"Sources: {', '.join([f'{k} ({v})' for k, v in sources.items()])}")
            
            return {
                'summary': '. '.join(summary_parts),
                'sentiment_score': round(avg_sentiment, 3),
                'sentiment_label': sentiment_label,
                'item_count': len(chatter_items)
            }
            
        except Exception as e:
            logger.warning(f"Failed to retrieve market chatter for {ticker}: {e}")
            return {
                'summary': f'Unable to retrieve market chatter for {ticker}',
                'sentiment_score': 0.0,
                'sentiment_label': 'neutral',
                'item_count': 0
            }
    
    def _get_latest_financial_metrics(self, ticker: str) -> Dict[str, Any]:
        """
        Get latest financial metrics from database.
        
        Args:
            ticker: Company ticker symbol
            
        Returns:
            Dictionary with latest financial metrics or structured object explaining unavailability
        """
        try:
            # Get latest quarterly financials
            balance_data, balance_status = VFISDataAccess.get_quarterly_financials(
                ticker=ticker,
                statement_type='balance_sheet',
                agent_name='FinalOutputAssembly',
                user_query='Get latest financial metrics'
            )
            
            income_data, income_status = VFISDataAccess.get_quarterly_financials(
                ticker=ticker,
                statement_type='income_statement',
                agent_name='FinalOutputAssembly',
                user_query='Get latest financial metrics'
            )
            
            if balance_status.value == 'SUCCESS' or income_status.value == 'SUCCESS':
                # Extract metrics from data dictionary
                balance_metrics = balance_data.get('metrics', []) if balance_status.value == 'SUCCESS' else []
                income_metrics = income_data.get('metrics', []) if income_status.value == 'SUCCESS' else []
                
                return {
                    'available': True,
                    'balance_sheet': balance_metrics if balance_status.value == 'SUCCESS' else None,
                    'income_statement': income_metrics if income_status.value == 'SUCCESS' else None,
                    'as_of_date': balance_data.get('as_of_date') or income_data.get('as_of_date'),
                    'data_source': balance_data.get('data_source') or income_data.get('data_source')
                }
            
            # Return structured object explaining why data is unavailable
            reasons = []
            if balance_status.value != 'SUCCESS':
                reasons.append(f'Balance sheet: {balance_status.value}')
            if income_status.value != 'SUCCESS':
                reasons.append(f'Income statement: {income_status.value}')
            
            return {
                'available': False,
                'reason': 'Financial data not available in database',
                'details': '; '.join(reasons) if reasons else 'No quarterly financial reports found',
                'suggestions': [
                    'Check if company data has been ingested',
                    'Verify ticker symbol is correct',
                    'Ensure financial reports are available for this company'
                ]
            }
            
        except Exception as e:
            logger.warning(f"Failed to retrieve financial metrics for {ticker}: {e}")
            return {
                'available': False,
                'reason': 'Error retrieving financial data',
                'details': str(e),
                'suggestions': [
                    'Check database connectivity',
                    'Verify ticker symbol is correct',
                    'Review system logs for details'
                ]
            }
    
    def _get_all_subscriber_views(self, ticker: str, user_query: str) -> Dict[str, Dict[str, Any]]:
        """
        Get subscriber views for all risk levels.
        
        Args:
            ticker: Company ticker symbol
            user_query: User query for audit logging
            
        Returns:
            Dictionary with subscriber views for each risk level
        """
        views = {}
        try:
            # Get views for each risk level
            for risk_level in [SubscriberRiskTolerance.LOW_RISK, SubscriberRiskTolerance.MODERATE_RISK, SubscriberRiskTolerance.HIGH_RISK]:
                match_result = self.subscriber_matcher.match_company_to_subscriber(
                    ticker=ticker,
                    subscriber_risk_tolerance=risk_level,
                    user_query=user_query
                )
                
                key = 'low_risk' if risk_level == SubscriberRiskTolerance.LOW_RISK else \
                      'moderate_risk' if risk_level == SubscriberRiskTolerance.MODERATE_RISK else 'high_risk'
                
                views[key] = {
                    'is_match': match_result.get('is_match', False),
                    'explanation': match_result.get('explanation', ''),
                    'company_risk_level': match_result.get('company_risk_level', 'UNKNOWN'),
                    'warning': match_result.get('warning')
                }
            
            return views
            
        except Exception as e:
            logger.warning(f"Failed to get subscriber views for {ticker}: {e}")
            return {
                'low_risk': {'is_match': False, 'explanation': 'Unable to determine', 'company_risk_level': 'UNKNOWN'},
                'moderate_risk': {'is_match': False, 'explanation': 'Unable to determine', 'company_risk_level': 'UNKNOWN'},
                'high_risk': {'is_match': False, 'explanation': 'Unable to determine', 'company_risk_level': 'UNKNOWN'}
            }

