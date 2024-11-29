from typing import Tuple, Dict, Any
import logging
from core.agents.base_agent import AIAgent
from core.agents.risk_agent import RiskAgent
from core.agents.lp_avax_agent import LiquidityProviderAgent
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
        self._lp_avax_agent = None
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
    def lp_avax_agent(self):
        if self._lp_avax_agent is None:
            self._lp_avax_agent = LiquidityProviderAgent()
        return self._lp_avax_agent

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
            
            message_lower = message.lower()

            print(context, "context check dude context man")
            # Route to appropriate agent
            if agent_type == "deployment":
                response = await self.deployment_agent.process_message(message, context)
            elif agent_type == "risk":
                response = await self.risk_agent.process_message(message, context)
            elif agent_type == "trading":
                if "avalanche" in message_lower or "avax" in message_lower:
                    response = await self.lp_avax_agent.process_message(message, context)
                elif "unichain" in message_lower:
                    # TODO: Implement UniChain LP agent
                    response = {"error": "UniChain LP functionality coming soon!"}
                else:
                    # If chain not specified, return available options
                    response = {
                        "message": """Please specify which chain you'd like to provide liquidity on:

                    Avalanche (AVAX) - Available now
                    • Trader Joe V2 pools on Avalanche
                    • Currently supporting AVAX-USDC and AVAX-USDT pairs
                    • Concentrated liquidity positions for better capital efficiency

                    UniChain - Coming soon
                    • UniChain DEX pools
                    • Multiple pairs with automated market making
                    • Yield farming opportunities"""
                    }
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