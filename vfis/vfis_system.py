"""
Verified Financial Intelligence System (VFIS) Main System.

This system provides financial data retrieval and summarization only.
NO trading logic, NO buy/sell signals, NO investment recommendations.
"""

from typing import Dict, Any, Optional

from vfis.agents.verified_data_agent import VerifiedDataAgent
from vfis.tools.llm_factory import create_azure_openai_llm
from tradingagents.database import init_database
from tradingagents.default_config import DEFAULT_CONFIG


class VFISSystem:
    """
    Main system class for Verified Financial Intelligence System.
    
    STRICT BOUNDARIES:
    - ONLY retrieves and summarizes financial data
    - NO trading logic
    - NO buy/sell signals
    - NO investment recommendations
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm_provider: str = "azure",
        model_name: Optional[str] = None,
        debug: bool = False
    ):
        """
        Initialize the VFIS system.
        
        Args:
            config: Configuration dictionary (defaults to DEFAULT_CONFIG)
            llm_provider: LLM provider (always "azure" for Azure OpenAI)
            model_name: Model name (ignored for Azure OpenAI, deployment name comes from env)
            debug: Enable debug mode
        """
        self.config = config or DEFAULT_CONFIG.copy()
        self.debug = debug
        
        # Initialize database connection
        init_database(self.config)
        
        # Initialize LLM (always Azure OpenAI)
        self.llm = create_azure_openai_llm(temperature=0)
    
    def analyze_company(
        self,
        company_ticker: str,
        analysis_date: str,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze financial data for a company.
        
        Args:
            company_ticker: Company ticker symbol (dynamically provided)
            analysis_date: Analysis date (yyyy-mm-dd format)
            query: Optional query to guide analysis
            
        Returns:
            Dictionary containing analysis results
        """
        # Create verified data agent
        agent = VerifiedDataAgent(
            llm=self.llm,
            company_ticker=company_ticker,
            analysis_date=analysis_date,
            config=self.config
        )
        
        # Perform analysis
        result = agent.analyze(query)
        
        return {
            "company": company_ticker,
            "analysis_date": analysis_date,
            "summary": result["summary"],
            "tool_calls": result.get("tool_calls", []),
        }
    
    def get_summary(
        self,
        company_ticker: str,
        analysis_date: str
    ) -> str:
        """
        Get a comprehensive financial data summary.
        
        Args:
            company_ticker: Company ticker symbol
            analysis_date: Analysis date (yyyy-mm-dd format)
            
        Returns:
            Formatted summary string
        """
        result = self.analyze_company(company_ticker, analysis_date)
        return result["summary"]


def create_vfis_system(
    config: Optional[Dict[str, Any]] = None,
    llm_provider: str = "azure",
    model_name: Optional[str] = None,
    debug: bool = False
) -> VFISSystem:
    """
    Factory function to create a VFIS system instance.
    
    Args:
        config: Configuration dictionary
        llm_provider: LLM provider name (always "azure" for Azure OpenAI)
        model_name: Model name (ignored for Azure OpenAI)
        debug: Enable debug mode
        
    Returns:
        VFISSystem instance
    """
    return VFISSystem(
        config=config,
        llm_provider=llm_provider,
        model_name=model_name,
        debug=debug
    )

