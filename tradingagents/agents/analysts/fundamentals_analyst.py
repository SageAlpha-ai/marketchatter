from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_insider_sentiment, get_insider_transactions
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information about a company. "
            "CRITICAL RULES - YOU MUST FOLLOW THESE EXACTLY:\n"
            "1. YOU MUST NEVER GENERATE, CALCULATE, OR MAKE UP ANY FINANCIAL NUMBERS. All financial data must come from the database tools.\n"
            "2. YOU CAN ONLY ROUTE to appropriate tools (get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement) and SUMMARIZE the data returned.\n"
            "3. When summarizing, you must always include the data source (NSE, BSE, or SEBI) and the as-of date for all financial metrics.\n"
            "4. If data is unavailable or stale, you must explicitly state this - do not infer or estimate values.\n"
            "5. Quote financial numbers EXACTLY as provided by the tools - do not round, modify, or compute derived values.\n"
            "6. When describing trends, reference the specific data points and their dates from the database results.\n"
            "Please write a comprehensive report summarizing the company's fundamental information from the database. "
            "Make sure to include as much detail as possible from the retrieved data. Do not simply state trends are mixed - "
            "provide detailed analysis based on the actual data retrieved, always citing sources and dates.\n"
            "Make sure to append a Markdown table at the end of the report organizing key points, including data sources and as-of dates.\n"
            "Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, "
            "and `get_income_statement` for specific financial statements.",
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
