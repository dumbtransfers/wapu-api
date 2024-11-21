from swarm import Agent, Swarm
from typing import Dict, Any
from datetime import datetime, timedelta
import numpy as np
from decimal import Decimal
from data.market_data import MarketDataService
from data.historical import HistoricalDataService

class RiskAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Sofia Risk Analyst",
            model="gpt-4",
            instructions="""You are an advanced LP strategy and risk analysis assistant that provides detailed pool analysis and recommendations.
            
            IMPORTANT FUNCTION USAGE RULES:
            1. ALWAYS use analyze_pool when questions involve pool analysis or LP opportunities
            2. ALWAYS use assess_risk when questions involve risk evaluation
            3. ALWAYS use get_historical_performance when questions about past performance
            4. ALWAYS use suggest_strategy when users ask for LP recommendations
            
            Examples:
            - "How risky is the AVAX-USDC pool?" -> use assess_risk
            - "What's the best LP strategy for ETH-USDT?" -> use suggest_strategy
            - "How has the AVAX-JOE pool performed?" -> use get_historical_performance
            - "Analyze the ETH-USDC pool" -> use analyze_pool
            
            Always provide comprehensive analysis with specific metrics and recommendations.""",
            functions=[
                self.analyze_pool,
                self.assess_risk,
                self.get_historical_performance,
                self.suggest_strategy
            ]
        )

    async def analyze_pool(self, pool_address: str) -> Dict[str, Any]:
        """Analyze pool metrics and performance
        
        Args:
            pool_address (str): The pool contract address
            
        Returns:
            Dict with comprehensive pool analysis
        """
        self.market_data = MarketDataService()
        self.historical_data = HistoricalDataService()

        print(pool_address, "checking if pool address is valid analyze_pool")
        try:
            # Get current pool data
            pool_data = await self.market_data.get_pool_metrics(pool_address)
            print(pool_data, "pool data at analyze_pool, get_pool_metrics")
            # Get historical performance
            historical = await self.historical_data.get_pool_history(pool_address)
            print(historical, "historical data at analyze_pool, get_pool_history")
            return {
                "success": True,
                "data": {
                    "current_metrics": {
                        "tvl": pool_data.tvl,
                        "volume_24h": pool_data.volume_24h,
                        "fees_24h": pool_data.fees_24h,
                        "apr": pool_data.apr,
                        "price_range": pool_data.price_range
                    },
                    "historical_performance": {
                        "avg_apr_7d": historical.avg_apr_7d,
                        "volume_trend": historical.volume_trend,
                        "il_7d": historical.impermanent_loss_7d
                    },
                    "analysis_timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def assess_risk(self, pool_address: str) -> Dict[str, Any]:
        """Evaluate pool risks and provide risk metrics
        
        Args:
            pool_address (str): The pool contract address
            
        Returns:
            Dict with risk assessment and metrics
        """
        self.market_data = MarketDataService()

        print(pool_address, "checking if pool address is valid at assess_risk")

        try:
            # Get risk metrics
            risk_data = await self.market_data.get_risk_metrics(pool_address)
            print(risk_data, "risk data at assess_risk")
            return {
                "success": True,
                "data": {
                    "risk_scores": {
                        "volatility_risk": risk_data.volatility_score,
                        "liquidity_risk": risk_data.liquidity_score,
                        "il_risk": risk_data.il_risk_score,
                        "overall_risk": risk_data.overall_risk
                    },
                    "risk_factors": risk_data.risk_factors,
                    "analysis_timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def suggest_strategy(self, 
                             pool_address: str,
                             risk_tolerance: str = "moderate") -> Dict[str, Any]:
        """Suggest optimal LP strategy based on pool analysis
        
        Args:
            pool_address (str): The pool contract address
            risk_tolerance (str): User's risk tolerance (conservative/moderate/aggressive)
            
        Returns:
            Dict with strategy recommendations
        """
        print(pool_address, risk_tolerance , "checking if pool address is valid at suggest_strategy")

        try:
            # Get pool analysis
            pool_analysis = await self.analyze_pool(pool_address)
            risk_assessment = await self.assess_risk(pool_address)
            
            if not pool_analysis["success"] or not risk_assessment["success"]:
                raise Exception("Failed to get pool data")
                
            return {
                "success": True,
                "data": {
                    "recommended_strategy": {
                        "price_range": self._calculate_price_range(
                            pool_analysis["data"],
                            risk_tolerance
                        ),
                        "position_size": self._suggest_position_size(
                            risk_assessment["data"],
                            risk_tolerance
                        ),
                        "rebalance_frequency": self._get_rebalance_frequency(
                            pool_analysis["data"]["current_metrics"]["volatility"]
                        )
                    },
                    "expected_returns": {
                        "estimated_apr": pool_analysis["data"]["current_metrics"]["apr"],
                        "estimated_il": risk_assessment["data"]["risk_scores"]["il_risk"],
                        "net_return": self._calculate_net_return(
                            pool_analysis["data"]["current_metrics"]["apr"],
                            risk_assessment["data"]["risk_scores"]["il_risk"]
                        )
                    },
                    "analysis_timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def process_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Process user messages and return appropriate analysis"""
        context = context or {}
        client = Swarm()
        
        # Add context to messages
        messages = [{"role": "user", "content": message}]
        if context:
            context_message = "Context information:\n"
            for key, value in context.items():
                context_message += f"- {key}: {value}\n"
            messages.insert(0, {"role": "system", "content": context_message})
        
        response = client.run(
            agent=self,
            messages=messages
        )
        
        result = {
            "response": response.messages[-1]["content"],
            "type": "risk_analysis",
            "data": {},
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "query": message,
                "context": context
            }
        }
        
        # Extract pool address and analysis type from message
        pool_address = self._extract_pool_address(message)
        if pool_address:
            if self._is_risk_query(message):
                risk_data = await self.assess_risk(pool_address)
                if risk_data["success"]:
                    result.update({
                        "type": "risk_assessment",
                        "data": risk_data["data"]
                    })
            elif self._is_strategy_query(message):
                strategy = await self.suggest_strategy(
                    pool_address,
                    context.get('risk_tolerance', 'moderate')
                )
                if strategy["success"]:
                    result.update({
                        "type": "strategy_recommendation",
                        "data": strategy["data"]
                    })
        
        return result

    async def get_historical_performance(self, pool_address: str) -> Dict[str, Any]:
        """Get detailed historical performance metrics for a pool
        
        Args:
            pool_address (str): The pool contract address
            
        Returns:
            Dict with historical performance metrics
        """
        self.historical_data = HistoricalDataService()

        print(pool_address , "checking if pool address is valid at get_historical_performance")

        try:
            # Get historical data
            historical = await self.historical_data.get_pool_history(pool_address)
            print(historical, "historical data at get_historical_performance")
            return {
                "success": True,
                "data": {
                    "performance_metrics": {
                        "avg_apr_7d": historical.avg_apr_7d,
                        "avg_apr_30d": historical.avg_apr_30d,
                        "volume_trend": historical.volume_trend,
                        "il_7d": historical.impermanent_loss_7d,
                        "il_30d": historical.impermanent_loss_30d,
                        "price_correlation": historical.price_correlation
                    },
                    "analysis_timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_pool_address(self, message: str) -> str:
        """Extract pool address from message using regex or simple parsing
        
        Args:
            message (str): The user's message
            
        Returns:
            str: Pool address if found, None otherwise
        """
        # Simple implementation - you might want to enhance this with regex
        # or more sophisticated parsing based on your needs
        words = message.lower().split()
        for word in words:
            # Check if word matches pool address format
            if word.startswith("0x") and len(word) == 42:
                return word
        return None

    def _is_risk_query(self, message: str) -> bool:
        """Check if message is asking about risk assessment
        
        Args:
            message (str): The user's message
            
        Returns:
            bool: True if message is about risk
        """
        risk_keywords = ["risk", "risky", "safe", "danger", "safety", "volatile"]
        return any(keyword in message.lower() for keyword in risk_keywords)

    def _is_strategy_query(self, message: str) -> bool:
        """Check if message is asking for strategy recommendations
        
        Args:
            message (str): The user's message
            
        Returns:
            bool: True if message is about strategy
        """
        print(message, "checking if message is about strategy at _is_strategy_query")
        strategy_keywords = ["strategy", "recommend", "suggestion", "best", "optimal"]
        return any(keyword in message.lower() for keyword in strategy_keywords)
