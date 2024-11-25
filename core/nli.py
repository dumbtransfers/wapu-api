from typing import Tuple, Dict, Any
import logging
from core.agents.base_agent import AIAgent
from core.agents.risk_agent import RiskAgent
from core.agents.trading_agent import TradingAgent

logger = logging.getLogger(__name__)

class NLIRouter:
    def __init__(self):
        self._base_agent = None
        self._risk_agent = None
        self._trading_agent = None
        
        # Keywords that indicate risk/LP related queries
        self.risk_keywords = {
            "risk", "risky", "safe", "safety", "volatile", "volatility",
            "impermanent", "il", "loss", "liquidity analysis", "pool analysis", 
            "apr", "yield", "returns", "strategy", "trader joe analysis", 
            "position analysis", "range analysis"
        }
        
        # Keywords that indicate price/crypto related queries
        self.price_keywords = {
            "price", "worth", "value", "cost", "btc", "eth", "bitcoin",
            "ethereum", "convert", "exchange", "dollar", "dolar", "usd",
            "rate", "cotización", "precio", "cuánto", "cuanto"
        }

        # Keywords that indicate trading/execution related queries
        self.trading_keywords = {
            "add liquidity", "remove liquidity", "swap", "trade", "provide liquidity",
            "withdraw", "deposit", "invest", "exit position", "enter position",
            "mint", "burn", "execute", "transaction"
        }

    @property
    def base_agent(self):
        if self._base_agent is None:
            self._base_agent = AIAgent()
        return self._base_agent

    @property
    def risk_agent(self):
        if self._risk_agent is None:
            self._risk_agent = RiskAgent()
        return self._risk_agent

    @property
    def trading_agent(self):
        if self._trading_agent is None:
            self._trading_agent = TradingAgent()
        return self._trading_agent

    async def route_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Route message to appropriate agent based on content analysis"""
        try:
            agent_type, confidence = self._analyze_message(message)
            logger.info(f"Routing message to {agent_type} agent with confidence {confidence}")
            
            # Only initialize and use the needed agent
            if agent_type == "risk":
                response = await self.risk_agent.process_message(message, context)
            elif agent_type == "trading":
                response = await self.trading_agent.process_message(message, context)
            else:
                response = await self.base_agent.process_message(message, context)
            
            # Add routing metadata to response
            if isinstance(response, dict):
                response["routing"] = {
                    "agent": agent_type,
                    "confidence": confidence
                }
            
            return response
            
        except Exception as e:
            logger.error(f"Error routing message: {str(e)}")
            return {
                "error": str(e),
                "routing": {
                    "agent": "error",
                    "confidence": 0
                }
            }

    def _analyze_message(self, message: str) -> Tuple[str, float]:
        """Analyze message to determine appropriate agent and confidence level"""
        message = message.lower()
        
        # First check for exact trading phrases
        if any(phrase in message for phrase in self.trading_keywords):
            return "trading", 1.0
            
        words = set(message.split())
        
        # Count matches for each category
        risk_matches = len(words.intersection(self.risk_keywords))
        price_matches = len(words.intersection(self.price_keywords))
        
        # Calculate confidence scores
        total_words = len(words)
        risk_confidence = risk_matches / total_words if total_words > 0 else 0
        price_confidence = price_matches / total_words if total_words > 0 else 0
        
        # Determine which agent to use based on highest confidence
        if risk_confidence > price_confidence:
            return "risk", risk_confidence
        else:
            return "base", price_confidence