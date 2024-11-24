from typing import Dict, Any, Optional,List, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
import aiohttp
from dataclasses import dataclass
from django.conf import settings
import asyncio
from web3 import Web3
from web3.providers import HTTPProvider
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider
import numpy as np
import logging

logger = logging.getLogger(__name__)

@dataclass
class PoolMetrics:
    """Data class for pool metrics"""
    tvl: Decimal
    volume_24h: Decimal
    fees_24h: Decimal
    apr: Decimal
    volatility: float
    price_range: Dict[str, Decimal]
    liquidity_distribution: Dict[str, Decimal]
    il_7d: float

@dataclass
class RiskMetrics:
    """Data class for risk metrics"""
    volatility_score: float
    liquidity_score: float
    il_risk_score: float
    overall_risk: float
    risk_factors: Dict[str, Any]

class MarketDataService:
    def __init__(self):
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(settings.AVALANCHE_RPC_URL))
        self.async_w3 = AsyncWeb3(AsyncHTTPProvider(settings.AVALANCHE_RPC_URL))

        # Convert pool address to checksum address
        self.pool_address = Web3.to_checksum_address(settings.AVAX_USDC_POOL)
        self.pool_abi = settings.TRADER_JOE_POOL_ABI
        
        logger.info(f"Initialized MarketDataService for AVAX-USDC pool: {self.pool_address}")
        
        # Initialize pool contract
        self.pool_contract = self.w3.eth.contract(
            address=self.pool_address,
            abi=self.pool_abi
        )
        
        # Cache settings
        self._metrics_cache = None
        self._metrics_timestamp = None
        self._cache_duration = 60  # seconds
        
    async def get_pool_metrics(self, pool_address: str = None) -> Dict:
        try:
            pool_contract = self.async_w3.eth.contract(
                address=self.pool_address,
                abi=self.pool_abi
            )
            
            # Get current price and TVL
            avax_price = await self._get_price_from_active_bin(pool_contract)
            avax_reserves, usdc_reserves = await self._calculate_tvl(pool_contract)
            tvl = (avax_reserves * avax_price) + usdc_reserves
            
            # Get current protocol fees
            protocol_fees = await pool_contract.functions.getProtocolFees().call()
            
            # Get static fee parameters to get protocol share
            static_fees = await pool_contract.functions.getStaticFeeParameters().call()
            protocol_share = Decimal(str(static_fees[5])) / Decimal('10000')
            
            # Calculate total fees
            fees_x = Decimal(str(protocol_fees[0])) / Decimal('1e18')
            fees_y = Decimal(str(protocol_fees[1])) / Decimal('1e6')
            
            total_fees_usd = (fees_x * avax_price) + fees_y
            if protocol_share > 0:
                total_fees_usd = total_fees_usd / protocol_share
            
            # Calculate fees for different periods
            fees_24h = total_fees_usd * Decimal('0.05')
            fees_7d = total_fees_usd * Decimal('0.25')
            
            # Calculate APRs
            apr_24h = Decimal('0')
            apr_7d = Decimal('0')
            if tvl > 0:
                apr_24h = (fees_24h * Decimal('365') / tvl) * Decimal('100')
                apr_7d = (fees_7d / tvl) * Decimal('52') * Decimal('100')
            
            # Calculate volatility
            volatility = await self._calculate_historical_volatility(pool_contract)
            
            # Debug prints
            print(f"Protocol Share: {protocol_share:.2%}")
            print(f"TVL: ${tvl:,.2f}")
            print(f"Total Fees (USD): ${total_fees_usd:,.2f}")
            print(f"24h Fees: ${fees_24h:,.2f}")
            print(f"7d Fees: ${fees_7d:,.2f}")
            print(f"APR (24h): {apr_24h:.2f}%")
            print(f"APR (7d): {apr_7d:.2f}%")
            
            # Return metrics in the expected structure
            metrics = {
                'tvl': str(tvl),
                'liquidity': {
                    'avax': str(avax_reserves),
                    'usdc': str(usdc_reserves)
                },
                'current_price': str(avax_price),
                'volume_24h': str(fees_24h * Decimal('20')),  # Estimate volume as 20x fees
                'fees_24h': str(fees_24h),
                'apr': str(apr_7d),  # Use 24h APR as default
                'apr_24h': str(apr_24h),
                'apr_7d': str(apr_7d),
                'volatility': float(volatility),
                'il_7d': float(volatility * 0.5),  # Estimate IL as half of volatility
                'price_range': {
                    'current': str(avax_price),
                    'min': str(avax_price * Decimal('0.9')),  # Example range
                    'max': str(avax_price * Decimal('1.1'))
                }
            }
            
            return metrics
                
        except Exception as e:
            logger.error(f"Error in get_pool_metrics: {str(e)}")
            return self._get_empty_metrics()

    async def get_risk_metrics(self, pool_address: str) -> RiskMetrics:
        """Calculate risk metrics for pool"""
        try:
            # Get pool metrics first
            pool_metrics = await self.get_pool_metrics(pool_address)
            
            # Calculate risk scores - access dictionary values instead of attributes
            volatility_score = self._calculate_volatility_score(pool_metrics['volatility'])
            liquidity_score = self._calculate_liquidity_score(Decimal(pool_metrics['tvl']))
            il_risk_score = self._calculate_il_risk_score(pool_metrics['il_7d'])
            
            # Calculate overall risk
            overall_risk = (volatility_score + liquidity_score + il_risk_score) / 3
            
            # Identify risk factors
            risk_factors = self._identify_risk_factors(pool_metrics)
            
            return RiskMetrics(
                volatility_score=volatility_score,
                liquidity_score=liquidity_score,
                il_risk_score=il_risk_score,
                overall_risk=overall_risk,
                risk_factors=risk_factors
            )
            
        except Exception as e:
            raise Exception(f"Error calculating risk metrics: {str(e)}")
            
    def _calculate_volatility_score(self, volatility: float) -> float:
        """Convert volatility to 0-1 risk score"""
        # Higher volatility = higher risk
        return min(volatility * 10, 1.0)  # Cap at 1.0
        
    def _calculate_liquidity_score(self, tvl: Decimal) -> float:
        """Convert TVL to 0-1 risk score"""
        # Lower TVL = higher risk
        min_tvl = Decimal('100000')  # $100k minimum
        return float(min(min_tvl / tvl, 1.0))  # Cap at 1.0
        
    def _calculate_il_risk_score(self, il_7d: float) -> float:
        """Convert IL to 0-1 risk score"""
        # Higher IL = higher risk
        return min(il_7d * 20, 1.0)  # Cap at 1.0
        
    def _identify_risk_factors(self, metrics: Dict) -> Dict[str, Any]:
        """Identify specific risk factors"""
        factors = {}
        
        # Check volatility
        if metrics['volatility'] > 0.02:  # 2%
            factors['high_volatility'] = {
                'level': 'high',
                'value': metrics['volatility']
            }
            
        # Check liquidity
        if Decimal(metrics['tvl']) < Decimal('100000'):
            factors['low_liquidity'] = {
                'level': 'high',
                'value': metrics['tvl']
            }
            
        # Check IL risk
        if metrics['il_7d'] > 0.05:  # 5%
            factors['high_il_risk'] = {
                'level': 'high',
                'value': metrics['il_7d']
            }
            
        return factors
        
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get data from cache if not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now().timestamp() - timestamp < self.cache_duration:
                return data
        return None
        
    def _add_to_cache(self, key: str, data: Any):
        """Add data to cache"""
        self.cache[key] = (data, datetime.now().timestamp()) 
        
    async def _get_price_from_active_bin(self, pool_contract) -> Decimal:
        """Get AVAX price from Chainlink oracle"""
        try:
            # Chainlink AVAX/USD Price Feed on Avalanche
            CHAINLINK_AVAX_USD = "0x0A77230d17318075983913bC2145DB16C7366156"
            
            oracle_contract = self.async_w3.eth.contract(
                address=CHAINLINK_AVAX_USD,
                abi=[{
                    "inputs": [],
                    "name": "latestRoundData",
                    "outputs": [
                        {"internalType": "uint80", "name": "roundId", "type": "uint80"},
                        {"internalType": "int256", "name": "answer", "type": "int256"},
                        {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
                        {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
                        {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"}
                    ],
                    "stateMutability": "view",
                    "type": "function"
                }]
            )
            
            # Get latest price data
            round_data = await oracle_contract.functions.latestRoundData().call()
            price = Decimal(str(round_data[1])) / Decimal('1e8')  # Chainlink uses 8 decimals
            
            print(f"AVAX Price from Chainlink: ${price} USD")
            return price
            
        except Exception as e:
            logger.error(f"Error getting price from Chainlink: {str(e)}")
            return Decimal('0')

    def _calculate_apr(self, data: Dict, onchain_data: Dict) -> Decimal:
        """Calculate APR based on fees and TVL"""
        try:
            # Get daily fees
            daily_fees_usd = Decimal(str(data['fees24h']))
            
            # Annualize
            yearly_fees = daily_fees_usd * 365
            
            # Calculate APR
            tvl = Decimal(str(data['tvlUSD']))
            if tvl > 0:
                apr = (yearly_fees / tvl) * 100
                return apr
            return Decimal('0')
            
        except Exception as e:
            raise Exception(f"Error calculating APR: {str(e)}")

    def _calculate_volatility_from_bins(self, bins: List[Dict]) -> float:
        """Calculate volatility from bin distribution"""
        try:
            prices = []
            for bin in bins:
                x = Decimal(str(bin['x']))
                y = Decimal(str(bin['y']))
                if y > 0 and x > 0:  # Only include valid prices
                    price = float(x) / float(y)
                    prices.append(price)
            
            if len(prices) < 2:  # Need at least 2 prices for volatility
                return 0.0
            
            # Calculate log returns, handling potential zeros
            prices = np.array(prices)
            returns = np.diff(np.log(prices[prices > 0]))
            
            if len(returns) > 0:
                return float(np.std(returns) * np.sqrt(365))
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating volatility from bins: {str(e)}")
            return 0.0

    def _calculate_il_risk_from_bins(self, bins: List[Dict]) -> float:
        """Calculate IL risk from bin distribution"""
        try:
            prices = []
            for bin in bins:
                x = Decimal(str(bin['x']))
                y = Decimal(str(bin['y']))
                if y > 0 and x > 0:  # Only include valid prices
                    price = float(x) / float(y)
                    prices.append(price)
            
            if len(prices) < 2:  # Need at least 2 prices
                return 0.0
            
            price_ratio = max(prices) / min(prices) if prices else 1.0
            if price_ratio <= 1.0:
                return 0.0
            
            il = 2 * np.sqrt(price_ratio) / (1 + price_ratio) - 1
            return float(abs(il))
            
        except Exception as e:
            logger.error(f"Error calculating IL risk from bins: {str(e)}")
            return 0.0

    def _process_liquidity_distribution(self, bins: List[Dict]) -> Dict[str, Decimal]:
        """Process liquidity distribution from bin data"""
        try:
            total_liquidity = sum(
                Decimal(str(bin['x'])) + Decimal(str(bin['y'])) 
                for bin in bins
            )
            
            distribution = {}
            if total_liquidity > 0:
                for bin in bins:
                    bin_liquidity = Decimal(str(bin['x'])) + Decimal(str(bin['y']))
                    distribution[str(bin['id'])] = bin_liquidity / total_liquidity
                    
            return distribution
            
        except Exception as e:
            logger.error(f"Error processing liquidity distribution: {str(e)}")
            return {}

    def _convert_distribution_to_strings(self, distribution: Dict[str, Decimal]) -> Dict[str, str]:
        """Convert Decimal values to strings for JSON serialization"""
        return {k: str(v) for k, v in distribution.items()}

    def _calculate_price_range(self, bins: List[Dict]) -> Dict[str, str]:
        """Calculate price range including depth information"""
        try:
            active_bin = None
            current_price = Decimal('0')
            
            # Find active bin (bin with both tokens)
            for bin in bins:
                x = Decimal(str(bin['x']))
                y = Decimal(str(bin['y']))
                if x > 0 and y > 0:
                    active_bin = bin
                    # Price = (x/10^18)/(y/10^6) = (x/y)*10^-12
                    current_price = (x * Decimal('1e-12')) / y
                    break
            
            if not active_bin:
                return {'min': '0', 'max': '0', 'current': '0'}
            
            # Calculate +/- 2% depth
            plus_2_percent = current_price * Decimal('1.02')
            minus_2_percent = current_price * Decimal('0.98')
            
            return {
                'current': str(current_price),
                'plus_2_percent': str(plus_2_percent),
                'minus_2_percent': str(minus_2_percent)
            }
        except Exception as e:
            logger.error(f"Error calculating price range: {str(e)}")
            return {'min': '0', 'max': '0', 'current': '0'}

    def _get_empty_metrics(self) -> Dict:
        """Return empty metrics structure"""
        return {
            'tvl': '0',
            'liquidity': {
                'avax': '0',
                'usdc': '0'
            },
            'current_price': '0',
            'volume_24h': '0',
            'fees_24h': '0',
            'apr': '0',
            'apr_24h': '0',
            'apr_7d': '0',
            'volatility': 0.0,
            'il_7d': 0.0,
            'price_range': {
                'current': '0',
                'min': '0',
                'max': '0'
            }
        }

    async def _calculate_tvl(self, pool_contract) -> Tuple[Decimal, Decimal]:
        """Get total reserves directly from getReserves()"""
        try:
            # Get total reserves directly from contract
            reserves = await pool_contract.functions.getReserves().call()
            
            # Adjust for decimals
            avax_reserves = Decimal(str(reserves[0])) / Decimal('1e18')  # Convert from wei to AVAX
            usdc_reserves = Decimal(str(reserves[1])) / Decimal('1e6')   # Convert from micro to USDC
            
            print(f"Total AVAX: {avax_reserves} AVAX")
            print(f"Total USDC: {usdc_reserves} USDC")
            
            return avax_reserves, usdc_reserves
            
        except Exception as e:
            logger.error(f"Error calculating tvl: {str(e)}")
            return Decimal('0'), Decimal('0')

    async def _calculate_historical_volatility(self, pool_contract) -> float:
        """Calculate volatility using 30 days of price data"""
        try:
            current_timestamp = int(datetime.now().timestamp())
            prices = []
            
            # Get 30 daily samples
            for days_ago in range(30):
                timestamp = current_timestamp - (days_ago * 24 * 60 * 60)
                sample = await pool_contract.functions.getOracleSampleAt(timestamp).call()
                
                if sample and sample[0] > 0:
                    price = float(sample[0]) / 1e18  # Adjust for decimals
                    prices.append(price)
            
            if len(prices) < 2:
                return 0.0
            
            # Calculate daily returns
            returns = np.diff(np.log(prices))
            
            # Annualized volatility
            daily_vol = np.std(returns)
            annual_vol = daily_vol * np.sqrt(365)
            
            return float(annual_vol)
            
        except Exception as e:
            logger.error(f"Error calculating historical volatility: {str(e)}")
            return 0.0