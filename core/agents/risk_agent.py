import logging
import sys
from swarm import Agent, Swarm
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import numpy as np
from decimal import Decimal
from data.market_data import MarketDataService
from data.historical import HistoricalDataService
from django.conf import settings
from pydantic import Field, ConfigDict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class RiskAgent(Agent):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Declare the fields we want to add
    market_data: Optional[MarketDataService] = Field(default=None)
    pool_data_cache: Optional[Dict] = Field(default=None)
    cache_timestamp: Optional[datetime] = Field(default=None)
    cache_duration: int = Field(default=60)

    def __init__(self):
        logger.info("="*50)
        logger.info("INITIALIZING RISK AGENT FOR AVAX-USDC POOL")
        logger.info("="*50)        
        super().__init__(
            name="Sofia Risk Analyst",
            model="gpt-4",
            instructions="""You are an advanced LP strategy and risk analysis assistant for the AVAX-USDC pool on Trader Joe.
            
            IMPORTANT FUNCTION USAGE RULES:
            1. ALWAYS use analyze_pool for AVAX-USDC pool analysis
            2. ALWAYS use assess_risk for AVAX-USDC risk evaluation
            3. ALWAYS use get_historical_performance for AVAX-USDC past performance
            4. ALWAYS use suggest_strategy for AVAX-USDC LP recommendations
            
            Examples:
            - "How risky is the AVAX-USDC pool?" -> use assess_risk
            - "What's the best LP strategy?" -> use suggest_strategy
            - "How has the pool performed?" -> use get_historical_performance
            - "Analyze the pool" -> use analyze_pool
            
            Always provide comprehensive analysis with specific metrics and recommendations.""",
            functions=[
                self.analyze_pool,
                self.assess_risk,
                self.get_historical_performance,
                self.suggest_strategy
            ]
        )
        # Initialize our custom fields
        object.__setattr__(self, 'market_data', MarketDataService())
        object.__setattr__(self, 'pool_data_cache', None)
        object.__setattr__(self, 'cache_timestamp', None)
        object.__setattr__(self, 'cache_duration', 60)

    async def _get_pool_data(self) -> Dict:
        """Get cached pool data or fetch new data"""
        try:
            now = datetime.now()
            
            # Check if cache exists and is still valid
            if (self.pool_data_cache is not None and 
                self.cache_timestamp is not None and 
                (now - self.cache_timestamp).seconds < self.cache_duration):
                logger.info("Using cached pool data")
                return self.pool_data_cache
            
            # Fetch new data
            logger.info("Fetching fresh pool data")
            pool_data = await self.market_data.get_pool_metrics()
            
            if not pool_data:
                raise Exception("Failed to fetch pool metrics")
                
            object.__setattr__(self, 'pool_data_cache', pool_data)
            object.__setattr__(self, 'cache_timestamp', now)
            return pool_data
                
        except Exception as e:
            logger.error(f"Error in _get_pool_data: {str(e)}")
            raise Exception("Failed to get pool data")

    async def analyze_pool(self) -> Dict[str, Any]:
        """Analyze AVAX-USDC pool metrics and performance"""
        logger.info("Analyzing AVAX-USDC pool")
        historical_data = HistoricalDataService()

        try:
            # Get pool data from cache or fresh
            pool_data = await self._get_pool_data()
            print("\n" + "="*50)
            logger.info(f"Pool metrics received: {pool_data}")
            print("="*50)

            # Get historical performance
            historical = await historical_data.get_pool_history()
            print("\n" + "="*50)
            logger.info(f"Historical data received: {historical}")
            print("="*50)

            return {
                "success": True,
                "data": {
                    "current_metrics": {
                        "tvl": pool_data['tvl'],
                        "liquidity": pool_data['liquidity'],
                        "current_price": pool_data['current_price'],
                        "volume_24h": pool_data['volume_24h'],
                        "fees_24h": pool_data['fees_24h'],
                        # Calculate APR from fees and TVL
                        "apr":pool_data['apr']
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
            logger.error(f"Error in analyze_pool: {str(e)}")
            return {"success": False, "error": str(e)}

    def _calculate_apr(self, pool_data: Dict) -> Decimal:
        """Calculate APR from daily fees and TVL"""
        try:
            daily_fees = Decimal(pool_data['fees_24h'])
            tvl = Decimal(pool_data['tvl'])
            
            if tvl > 0:
                # Annualize the daily fees
                yearly_fees = daily_fees * 365
                apr = (yearly_fees / tvl) * 100
                return apr
            return Decimal('0')
        except Exception as e:
            logger.error(f"Error calculating APR: {str(e)}")
            return Decimal('0')

    async def assess_risk(self) -> Dict[str, Any]:
        """Evaluate AVAX-USDC pool risks and provide risk metrics"""
        logger.info("Assessing risk for AVAX-USDC pool")

        try:
            # Use cached pool data
            pool_data = await self._get_pool_data()
            
            # Calculate risk metrics
            risk_data = await self.market_data.get_risk_metrics(settings.AVAX_USDC_POOL)
            logger.info(f"Risk metrics received: {risk_data}")
            
            return {
                "success": True,
                "data": {
                    "risk_scores": {
                        "volatility_risk": risk_data.volatility_score,
                        "liquidity_risk": risk_data.liquidity_score,
                        "overall_risk": risk_data.overall_risk
                    },
                    "risk_factors": risk_data.risk_factors,
                    "analysis_timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def suggest_strategy(self, risk_tolerance: str = "moderate") -> Dict[str, Any]:
        """Suggest optimal LP strategy for AVAX-USDC pool"""
        logger.info(f"Suggesting strategy for AVAX-USDC pool with risk tolerance: {risk_tolerance}")

        try:
            # Get pool analysis
            pool_analysis = await self.analyze_pool()
            risk_assessment = await self.assess_risk()
            
            print(f"\nPool analysis: {pool_analysis}")
            print(f"\nRisk assessment: {risk_assessment}")
            if not pool_analysis["success"] or not risk_assessment["success"]:
                raise Exception("Failed to get pool data")
            
            volatility = risk_assessment["data"]["risk_scores"]["volatility_risk"]
            il_risk = risk_assessment["data"]["risk_scores"].get("il_risk_score", 0)

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
                            volatility
                        )
                    },
                    "expected_returns": {
                        "estimated_apr": pool_analysis["data"]["current_metrics"]["apr"],
                        "estimated_il": il_risk,
                        "net_return": self._calculate_net_return(
                            pool_analysis["data"]["current_metrics"]["apr"],
                            il_risk
                        )
                    },
                    "analysis_timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_historical_performance(self) -> Dict[str, Any]:
        """Get historical performance metrics for AVAX-USDC pool"""
        print("\n" + "="*50)
        print("GETTING HISTORICAL PERFORMANCE FOR AVAX-USDC POOL")
        print("="*50)
        historical_data = HistoricalDataService()
        try:
            historical = await historical_data.get_pool_history()
            print(f"\nHistorical data received: {historical}")
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
            print(f"\nERROR in get_historical_performance: {str(e)}")
            return {"success": False, "error": str(e)}

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
        logger.info(f"Checking if message is strategy query: {message}")
        strategy_keywords = ["strategy", "recommend", "suggestion", "best", "optimal"]
        result = any(keyword in message.lower() for keyword in strategy_keywords)
        logger.info(f"Is strategy query: {result}")
        return result

    async def process_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Process user messages and return appropriate analysis"""
        try:
            logger.info(f"Processing message: {message}")
            context = context or {}
            
            # Get strategy data
            strategy_data = await self.suggest_strategy(context.get('risk_tolerance', 'moderate'))
            pool_analysis = await self.analyze_pool()
            risk_assessment = await self.assess_risk()
            
            if not strategy_data["success"]:
                raise Exception(strategy_data["error"])
            
            # Format metrics with sanity checks - UPDATED THIS SECTION
            try:
                tvl = float(pool_analysis["data"]["current_metrics"]["tvl"])
                apr = float(pool_analysis["data"]["current_metrics"]["apr"])  # Changed from historical
                il_risk = 0.1  # Default IL risk since we don't have historical yet
                volume_trend = {"trend": "stable", "change": 0.0}  # Default volume trend
                overall_risk = risk_assessment["data"]["risk_scores"]["overall_risk"]
            except Exception as e:
                logger.error(f"Error parsing metrics: {str(e)}")
                raise Exception("Failed to parse pool metrics")

            print(f"Pool Analysis Data: {pool_analysis['data']}")
            
            # Sanity check APR
            if apr > 1000:  # Cap unrealistic APR
                apr = 1000
            
            # Calculate realistic net return
            net_return = apr * (1 - il_risk)
            
            response_text = f"""Based on my analysis of the AVAX-USDC pool:

💰 Pool Overview:
• Total Value Locked: ${tvl:,.2f}
• Current APR: {apr:.2f}%
• Volume Trend: {volume_trend['trend'].title()} ({volume_trend['change']:.1f}% change)

⚠️ Risk Assessment:
• Overall Risk Level: {"Low" if overall_risk < 0.3 else "Moderate" if overall_risk < 0.6 else "High"}
• Impermanent Loss Risk: {il_risk*100:.1f}%
• Liquidity Risk: {risk_assessment["data"]["risk_scores"]["liquidity_risk"]*100:.1f}%

📊 Strategy Recommendation:
• Position Size: {(1-overall_risk)*100:.1f}% of your target allocation
• Rebalance Frequency: {self._get_rebalance_frequency(risk_assessment["data"]["risk_scores"]["volatility_risk"])}
• Expected Net Return: {net_return:.2f}%

🔍 Key Considerations:
• {"High IL risk - consider narrower price ranges" if il_risk > 0.1 else "Moderate IL risk - standard price ranges acceptable"}
• {"Low liquidity - enter positions gradually" if risk_assessment["data"]["risk_scores"]["liquidity_risk"] > 0.5 else "Good liquidity - can enter positions normally"}
• {"Decreasing volume - monitor closely" if volume_trend['trend'] == "decreasing" else "Stable/Increasing volume - healthy trading activity"}
"""

            return {
                "success": True,
                "type": "strategy_recommendation",
                "data": strategy_data["data"],
                "response": response_text,
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "query": message,
                    "context": context
                }
            }

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "type": "error",
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "query": message,
                    "context": context
                }
            }

    def _calculate_price_range(self, pool_data: Dict, risk_tolerance: str) -> Dict[str, float]:
        """Calculate recommended price range based on pool data and risk tolerance"""
        try:
            current_price = float(pool_data['current_metrics']['price_range']['current'])
            
            ranges = {
                'conservative': 0.05,  # ±5%
                'moderate': 0.10,     # ±10%
                'aggressive': 0.20    # ±20%
            }
            
            range_multiplier = ranges.get(risk_tolerance, ranges['moderate'])
            
            # Convert to USDC prices (1/price for AVAX/USDC pair)
            current_usdc = 1 / current_price
            print(current_price, "current price at calculate_price_rage")
            print(current_usdc, "current usdc at calculate_price_rage")
            return {
                'min_usdc': 1 / (current_price * (1 + range_multiplier)),  # Lower USDC price
                'max_usdc': 1 / (current_price * (1 - range_multiplier)),  # Upper USDC price
                'current_usdc': current_usdc
            }
        except Exception as e:
            logger.error(f"Error calculating price range: {str(e)}")
            return {'min_usdc': 0, 'max_usdc': 0, 'current_usdc': 0}

    def _suggest_position_size(self, risk_data: Dict, risk_tolerance: str) -> Dict[str, Any]:
        """Suggest position size based on risk assessment"""
        try:
            # Base position sizes on risk tolerance
            max_positions = {
                'conservative': 0.3,  # 30% of portfolio
                'moderate': 0.5,      # 50% of portfolio
                'aggressive': 0.7     # 70% of portfolio
            }
            
            base_size = max_positions.get(risk_tolerance, max_positions['moderate'])
            
            # Adjust based on risk scores
            overall_risk = risk_data['risk_scores']['overall_risk']
            adjusted_size = base_size * (1 - overall_risk)
            
            return {
                'recommended_size': adjusted_size,
                'max_size': base_size,
                'risk_adjustment': -overall_risk
            }
        except Exception as e:
            logger.error(f"Error suggesting position size: {str(e)}")
            return {'recommended_size': 0, 'max_size': 0, 'risk_adjustment': 0}

    def _get_rebalance_frequency(self, volatility: float) -> str:
        """Determine rebalance frequency based on volatility"""
        try:
            if volatility > 0.05:  # High volatility
                return "daily"
            elif volatility > 0.02:  # Medium volatility
                return "weekly"
            else:  # Low volatility
                return "monthly"
        except Exception as e:
            logger.error(f"Error getting rebalance frequency: {str(e)}")
            return "weekly"

    def _calculate_net_return(self, apr: str, il_risk: float) -> float:
        """Calculate estimated net return accounting for IL risk"""
        try:
            estimated_apr = float(apr)
            net_return = estimated_apr * (1 - il_risk)
            return max(0, net_return)  # Ensure non-negative return
        except Exception as e:
            logger.error(f"Error calculating net return: {str(e)}")
            return 0.0
