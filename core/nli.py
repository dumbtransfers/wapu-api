from typing import Tuple, Dict, Any
import logging
from core.agents.base_agent import AIAgent
from core.agents.risk_agent import RiskAgent
from core.agents.trading_agent import TradingAgent
from core.agents.image_agent import ImageAgent
from core.agents.deployment_agent import DeploymentAgent
from core.agents.router_agent import RouterAgent
from swarm import Swarm

logger = logging.getLogger(__name__)

class NLIRouter:
    def __init__(self):
        self._router_agent = None
        self._base_agent = None
        self._risk_agent = None
        self._trading_agent = None
        self._image_agent = None
        self._deployment_agent = None

    @property
    def router_agent(self):
        if self._router_agent is None:
            self._router_agent = RouterAgent()
        return self._router_agent

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

    @property
    def image_agent(self):
        if self._image_agent is None:
            self._image_agent = ImageAgent()
        return self._image_agent

    @property
    def deployment_agent(self):
        if self._deployment_agent is None:
            self._deployment_agent = DeploymentAgent()
        return self._deployment_agent

    async def route_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Route message to appropriate agent based on AI analysis"""
        try:
            routing = await self.router_agent.analyze_intent(message, context)
                        # Get the routing info from the tool calls
            print(routing, "check routing")

            agent_type = routing["agent_type"]
            confidence = routing["confidence"]
            
            logger.info(f"Routing message to {agent_type} agent with confidence {confidence}")
            logger.info(f"Reasoning: {routing['reasoning']}")
            
            print(context, "context check dude context man")
            # Route to appropriate agent
            if agent_type == "deployment":
                response = await self.deployment_agent.process_message(message, context)
            elif agent_type == "risk":
                response = await self.risk_agent.process_message(message, context)
            elif agent_type == "trading":
                response = await self.trading_agent.process_message(message, context)
            elif agent_type == "image":
                response = await self.image_agent.process_message(message, context)
            else:
                response = await self.base_agent.process_message(message, context)
            
            # Add routing metadata
            if isinstance(response, dict):
                response["routing"] = {
                    "agent": agent_type,
                    "confidence": confidence,
                    "reasoning": routing["reasoning"]
                }
            
            return response
            
        except Exception as e:
            logger.error(f"Error routing message: {str(e)}")
            return {
                "error": str(e),
                "routing": {
                    "agent": "error",
                    "confidence": 0,
                    "reasoning": str(e)
                }
            }