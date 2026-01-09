"""
Verified Data Agent for Verified Financial Intelligence System.

This agent is responsible ONLY for retrieving financial data via tools
and summarizing it. It does NOT generate financial numbers, make trading
decisions, or provide investment recommendations.

STRICT BOUNDARIES:
- ONLY retrieves data via tools
- ONLY summarizes retrieved data
- NEVER generates or calculates financial numbers
- NEVER provides trading signals or recommendations
"""

from typing import Dict, Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, ToolMessage
from pathlib import Path

from vfis.prompts.data_agent_prompts import (
    VERIFIED_DATA_AGENT_SYSTEM_PROMPT,
    TOOL_SELECTION_PROMPT,
    SUMMARY_GUIDELINES
)
from vfis.tools import (
    get_fundamentals,
    get_balance_sheet,
    get_income_statement,
    get_cashflow
)


class VerifiedDataAgent:
    """
    Agent that retrieves and summarizes financial data from PostgreSQL.
    
    CRITICAL RESTRICTIONS:
    - NEVER generates financial numbers
    - ONLY uses tools to retrieve data
    - ONLY summarizes retrieved data
    - NO trading logic or recommendations
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        company_ticker: str,
        analysis_date: str,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Verified Data Agent.
        
        Args:
            llm: Language model for summarization (MUST NOT generate numbers)
            company_ticker: Company ticker symbol (dynamically provided)
            analysis_date: Date for analysis (yyyy-mm-dd format)
            config: Optional configuration dictionary
        """
        self.llm = llm
        self.company_ticker = company_ticker.upper()
        self.analysis_date = analysis_date
        self.config = config or {}
        
        # Available tools - ONLY financial data retrieval tools
        self.tools = [
            get_fundamentals,
            get_balance_sheet,
            get_income_statement,
            get_cashflow,
        ]
        
        # Create prompt template
        self.prompt = self._create_prompt()
        
        # Create chain with tools
        self.chain = self.prompt | self.llm.bind_tools(self.tools)
    
    def _create_prompt(self) -> ChatPromptTemplate:
        """Create the prompt template with strict restrictions."""
        return ChatPromptTemplate.from_messages([
            (
                "system",
                f"""{VERIFIED_DATA_AGENT_SYSTEM_PROMPT}

{TOOL_SELECTION_PROMPT}

{SUMMARY_GUIDELINES}

CURRENT CONTEXT:
- Company: {self.company_ticker}
- Analysis Date: {self.analysis_date}

Remember: You are ONLY retrieving and summarizing data. NO financial number generation. NO trading recommendations."""
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])
    
    def analyze(self, query: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze financial data for the company.
        
        Args:
            query: Optional query to guide analysis (e.g., "Get balance sheet data")
            
        Returns:
            Dictionary containing:
                - summary: Text summary of the financial data
                - tool_calls: List of tools that were called
                - data_sources: List of data sources used
        """
        # Default query if none provided
        if query is None:
            query = f"Retrieve and summarize comprehensive financial data for {self.company_ticker}"
        
        # Create initial message
        messages = [
            HumanMessage(content=query)
        ]
        
        # Invoke the chain with tool execution
        # CRITICAL: This handles tool calls iteratively to ensure data comes from tools only
        # PROHIBITED: LLM must NEVER generate financial numbers - all data must come from tools
        result = self.chain.invoke({"messages": messages})
        
        # Handle tool calls if present
        # CRITICAL: Tool execution ensures all data comes from PostgreSQL, not LLM generation
        tool_calls = []
        final_summary = ""
        current_messages = messages.copy()
        max_iterations = 5  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            result = self.chain.invoke({"messages": current_messages})
            current_messages.append(result)
            
            if hasattr(result, 'tool_calls') and result.tool_calls:
                # Execute tools - THIS IS WHERE DATA COMES FROM (PostgreSQL via tools)
                tool_calls.extend(result.tool_calls)
                tool_messages = []
                
                for tool_call in result.tool_calls:
                    tool_name = tool_call.get('name', '')
                    tool_args = tool_call.get('args', {})
                    tool_call_id = tool_call.get('id', '')
                    
                    # Find and execute the tool
                    tool_func = next((t for t in self.tools if t.name == tool_name), None)
                    if tool_func:
                        try:
                            # CRITICAL: Tool execution retrieves data from PostgreSQL
                            tool_result = tool_func.invoke(tool_args)
                            tool_messages.append(
                                ToolMessage(content=str(tool_result), tool_call_id=tool_call_id)
                            )
                        except Exception as e:
                            tool_messages.append(
                                ToolMessage(content=f"Error: {str(e)}", tool_call_id=tool_call_id)
                            )
                
                current_messages.extend(tool_messages)
            else:
                # No more tool calls, we have the final summary
                final_summary = result.content if hasattr(result, 'content') else str(result)
                break
        
        if not final_summary:
            final_summary = "Analysis incomplete. Please check tool execution."
        
        return {
            "summary": final_summary,
            "tool_calls": tool_calls,
            "company": self.company_ticker,
            "analysis_date": self.analysis_date,
        }
    
    def get_summary(self) -> str:
        """
        Get a comprehensive financial data summary.
        
        Returns:
            Formatted summary string with all financial data
        """
        result = self.analyze("Retrieve and summarize all available financial data")
        return result["summary"]


def create_verified_data_agent(
    llm: BaseChatModel,
    company_ticker: str,
    analysis_date: str,
    config: Optional[Dict[str, Any]] = None
) -> VerifiedDataAgent:
    """
    Factory function to create a Verified Data Agent.
    
    Args:
        llm: Language model instance
        company_ticker: Company ticker symbol
        analysis_date: Analysis date (yyyy-mm-dd)
        config: Optional configuration
        
    Returns:
        VerifiedDataAgent instance
    """
    return VerifiedDataAgent(
        llm=llm,
        company_ticker=company_ticker,
        analysis_date=analysis_date,
        config=config
    )

