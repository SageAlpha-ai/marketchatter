"""
Debate Orchestrator for VFIS - Coordinates Bull vs Bear debate.

STRICT RULES:
- Output must be structured, not narrative
- All facts from PostgreSQL with citations
- LLMs never generate financial numbers
- Both perspectives must be represented
"""

import logging
from typing import Dict, Any, Optional
from datetime import date

from vfis.agents.bull_agent import BullAgent
from vfis.agents.bear_agent import BearAgent
from tradingagents.database.audit import log_data_access

logger = logging.getLogger(__name__)


class DebateOrchestrator:
    """
    Orchestrates debate between Bull and Bear agents.
    
    CRITICAL: Provides structured output comparing both perspectives.
    """
    
    def __init__(self, llm_model: Optional[str] = None):
        """
        Initialize Debate Orchestrator.
        
        Args:
            llm_model: LLM model name for agents
        """
        self.bull_agent = BullAgent(llm_model=llm_model)
        self.bear_agent = BearAgent(llm_model=llm_model)
    
    def conduct_debate(
        self,
        ticker: str,
        user_query: str = "Conduct bull vs bear debate"
    ) -> Dict[str, Any]:
        """
        Conduct structured debate between Bull and Bear agents.
        
        Args:
            ticker: Company ticker symbol
            user_query: Original user query
            
        Returns:
            Structured debate output with both perspectives
        """
        try:
            # Get Bull perspective
            bull_signals = self.bull_agent.analyze_positive_signals(
                ticker=ticker,
                user_query=user_query
            )
            
            # Get Bear perspective
            bear_signals = self.bear_agent.analyze_risk_signals(
                ticker=ticker,
                user_query=user_query
            )
            
            # Assemble structured debate output
            debate_output = {
                'ticker': ticker,
                'analysis_date': date.today().isoformat(),
                'debate_format': 'structured',
                'bull_perspective': {
                    'agent_name': bull_signals.get('agent_name', 'BullAgent'),
                    'positive_signals_count': len(bull_signals.get('positive_signals', [])),
                    'key_signals': bull_signals.get('positive_signals', [])[:5],  # Top 5
                    'data_sources': bull_signals.get('data_sources', []),
                    'citations': bull_signals.get('citations', []),
                    'warnings': bull_signals.get('warnings', []),
                    'summary': bull_signals.get('llm_summary', '')
                },
                'bear_perspective': {
                    'agent_name': bear_signals.get('agent_name', 'BearAgent'),
                    'risk_signals_count': len(bear_signals.get('risk_signals', [])),
                    'key_risks': bear_signals.get('risk_signals', [])[:5],  # Top 5
                    'data_sources': bear_signals.get('data_sources', []),
                    'citations': bear_signals.get('citations', []),
                    'warnings': bear_signals.get('warnings', []),
                    'summary': bear_signals.get('llm_summary', '')
                },
                'data_quality': {
                    'bull_data_sources': len(bull_signals.get('data_sources', [])),
                    'bear_data_sources': len(bear_signals.get('data_sources', [])),
                    'combined_warnings': list(set(
                        bull_signals.get('warnings', []) + 
                        bear_signals.get('warnings', [])
                    ))
                },
                'citations': {
                    'bull_citations': bull_signals.get('citations', []),
                    'bear_citations': bear_signals.get('citations', [])
                }
            }
            
            # Log debate execution
            log_data_access(
                event_type='debate_execution',
                entity_type='ticker_analysis',
                entity_id=None,
                details={
                    'ticker': ticker,
                    'bull_signals': debate_output['bull_perspective']['positive_signals_count'],
                    'bear_signals': debate_output['bear_perspective']['risk_signals_count']
                },
                user_id='DebateOrchestrator'
            )
            
            return debate_output
        
        except Exception as e:
            logger.error(f"Debate orchestration failed for {ticker}: {e}", exc_info=True)
            log_data_access(
                event_type='debate_error',
                entity_type='ticker_analysis',
                entity_id=None,
                details={'ticker': ticker, 'error': str(e)},
                user_id='DebateOrchestrator'
            )
            return {
                'ticker': ticker,
                'analysis_date': date.today().isoformat(),
                'error': str(e),
                'debate_format': 'structured',
                'bull_perspective': {},
                'bear_perspective': {}
            }

