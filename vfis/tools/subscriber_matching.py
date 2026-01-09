"""
Subscriber Risk Matching for VFIS.

STRICT RULES:
- Low-risk users see only LOW-risk companies
- Moderate-risk users see LOW and MODERATE
- High-risk users see all companies
- No LLM logic, pure deterministic matching
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from vfis.agents.risk_management_agent import RiskManagementAgent, RiskLevel

logger = logging.getLogger(__name__)


class SubscriberRiskTolerance(Enum):
    """Subscriber risk tolerance types."""
    LOW_RISK = "Low Risk"
    MODERATE_RISK = "Moderate Risk"
    HIGH_RISK = "High Risk"


class SubscriberMatcher:
    """
    Matches companies to subscribers based on risk tolerance.
    
    CRITICAL: Deterministic matching rules, no LLM logic.
    """
    
    def __init__(self):
        """Initialize Subscriber Matcher."""
        self.risk_agent = RiskManagementAgent()
    
    def match_company_to_subscriber(
        self,
        ticker: str,
        subscriber_risk_tolerance: SubscriberRiskTolerance,
        user_query: str = "Match company to subscriber"
    ) -> Dict[str, Any]:
        """
        Determine if a company matches subscriber's risk tolerance.
        
        Args:
            ticker: Company ticker symbol
            subscriber_risk_tolerance: Subscriber's risk tolerance level
            user_query: Original user query for audit logging
            
        Returns:
            Dictionary with matching result and explanation
        """
        try:
            # Get company risk classification
            risk_assessment = self.risk_agent.classify_risk(
                ticker=ticker,
                user_query=user_query
            )
            
            risk_level_str = risk_assessment.get('risk_level', 'UNKNOWN')
            try:
                company_risk_level = RiskLevel[risk_level_str]
            except KeyError:
                # If risk level is not a valid enum value, default to HIGH for safety
                logger.warning(f"Invalid risk level '{risk_level_str}', defaulting to HIGH")
                company_risk_level = RiskLevel.HIGH
            
            # Deterministic matching rules
            is_match, warning = self._check_match(company_risk_level, subscriber_risk_tolerance)
            
            result = {
                'ticker': ticker,
                'subscriber_risk_tolerance': subscriber_risk_tolerance.value,
                'company_risk_level': company_risk_level.value,
                'is_match': is_match,
                'warning': warning,
                'matching_rules': self._get_matching_rules(),
                'explanation': self._generate_explanation(
                    is_match, company_risk_level, subscriber_risk_tolerance, warning
                ),
                'risk_assessment': risk_assessment
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Subscriber matching failed for {ticker}: {e}", exc_info=True)
            return {
                'ticker': ticker,
                'subscriber_risk_tolerance': subscriber_risk_tolerance.value,
                'is_match': False,
                'error': str(e),
                'explanation': f"Matching failed: {str(e)}"
            }
    
    def _check_match(
        self,
        company_risk: RiskLevel,
        subscriber_tolerance: SubscriberRiskTolerance
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if company risk matches subscriber tolerance.
        
        Rules:
        - LOW_RISK subscribers: Only LOW risk companies (perfect match)
        - MODERATE_RISK subscribers: LOW and MODERATE risk companies (perfect match)
        - HIGH_RISK subscribers: MODERATE and HIGH risk companies (perfect match)
        - HIGH_RISK subscribers can accept LOW risk companies but with "low upside" warning
        
        Returns:
            Tuple of (is_match: bool, warning: Optional[str])
        """
        if subscriber_tolerance == SubscriberRiskTolerance.LOW_RISK:
            return (company_risk == RiskLevel.LOW, None)
        
        elif subscriber_tolerance == SubscriberRiskTolerance.MODERATE_RISK:
            if company_risk == RiskLevel.LOW:
                return (True, None)  # Perfect match
            elif company_risk == RiskLevel.MODERATE:
                return (True, None)  # Perfect match
            else:
                return (False, None)  # HIGH risk not acceptable
        
        elif subscriber_tolerance == SubscriberRiskTolerance.HIGH_RISK:
            if company_risk == RiskLevel.LOW:
                return (True, "Low upside potential - LOW risk company may not align with high-risk investment goals")
            elif company_risk in [RiskLevel.MODERATE, RiskLevel.HIGH]:
                return (True, None)  # Perfect match
            else:
                return (False, None)
        
        else:
            return (False, None)
    
    def _get_matching_rules(self) -> Dict[str, List[str]]:
        """Get matching rules for documentation."""
        return {
            'Low Risk Subscribers': ['LOW risk companies only'],
            'Moderate Risk Subscribers': ['LOW and MODERATE risk companies'],
            'High Risk Subscribers': ['All companies (LOW, MODERATE, HIGH)']
        }
    
    def _generate_explanation(
        self,
        is_match: bool,
        company_risk: RiskLevel,
        subscriber_tolerance: SubscriberRiskTolerance,
        warning: Optional[str] = None
    ) -> str:
        """Generate explanation of matching result."""
        if is_match:
            base_explanation = (
                f"Company risk level ({company_risk.value}) is acceptable for "
                f"subscriber risk tolerance ({subscriber_tolerance.value})."
            )
            if warning:
                return f"{base_explanation} {warning}"
            else:
                return f"{base_explanation} This company aligns well with this subscriber's risk profile."
        else:
            return (
                f"Company risk level ({company_risk.value}) does not align with "
                f"subscriber risk tolerance ({subscriber_tolerance.value}). "
                f"This company is NOT recommended for this subscriber."
            )
    
    def filter_companies_by_subscriber(
        self,
        tickers: List[str],
        subscriber_risk_tolerance: SubscriberRiskTolerance,
        user_query: str = "Filter companies by subscriber"
    ) -> Dict[str, Any]:
        """
        Filter list of companies based on subscriber risk tolerance.
        
        Args:
            tickers: List of company ticker symbols
            subscriber_risk_tolerance: Subscriber's risk tolerance level
            user_query: Original user query for audit logging
            
        Returns:
            Dictionary with filtered results
        """
        matching_tickers = []
        non_matching_tickers = []
        errors = []
        
        for ticker in tickers:
            try:
                match_result = self.match_company_to_subscriber(
                    ticker=ticker,
                    subscriber_risk_tolerance=subscriber_risk_tolerance,
                    user_query=user_query
                )
                
                if match_result.get('is_match', False):
                    matching_tickers.append(ticker)
                else:
                    non_matching_tickers.append({
                        'ticker': ticker,
                        'reason': match_result.get('explanation', 'Unknown')
                    })
            
            except Exception as e:
                errors.append({'ticker': ticker, 'error': str(e)})
                logger.warning(f"Failed to match {ticker}: {e}")
        
        return {
            'subscriber_risk_tolerance': subscriber_risk_tolerance.value,
            'total_companies': len(tickers),
            'matching_companies': len(matching_tickers),
            'non_matching_companies': len(non_matching_tickers),
            'matching_tickers': matching_tickers,
            'non_matching_details': non_matching_tickers,
            'errors': errors
        }

