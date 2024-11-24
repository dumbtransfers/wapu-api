from typing import Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
import numpy as np
from django.conf import settings
from web3 import Web3, AsyncWeb3
from web3.providers import AsyncHTTPProvider
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class HistoricalMetrics:
    """Data class for historical metrics"""
    avg_apr_7d: float
    avg_apr_30d: float
    volume_trend: Dict[str, Any]
    impermanent_loss_7d: float
    impermanent_loss_30d: float
    price_correlation: float
    price_volatility: float
    key_levels: Dict[str, Decimal]

class HistoricalDataService:
    def __init__(self):
        # Initialize Web3
        self.w3 = AsyncWeb3(AsyncHTTPProvider(settings.AVALANCHE_RPC_URL))
        
        # Initialize contracts - Only AVAX-USDC pool
        self.pool_abi = settings.TRADER_JOE_POOL_ABI
        # Convert to checksum address
        self.pool_address = Web3.to_checksum_address(settings.AVAX_USDC_POOL)
        
        logger.info(f"Initialized HistoricalDataService for AVAX-USDC pool: {self.pool_address}")

        self._history_cache = None
        self._history_timestamp = None
        self._cache_duration = 300  # 5 minutes for historical data

    async def get_pool_history(self, pool_address: str = None) -> HistoricalMetrics:
        """Get historical pool data with caching"""
        now = datetime.now()
        
        # Check cache
        if (self._history_cache is not None and 
            self._history_timestamp is not None and 
            (now - self._history_timestamp).seconds < self._cache_duration):
            logger.info("Using cached historical data")
            return self._history_cache

        # Fetch new data
        logger.info("Fetching fresh historical data")
        try:
            # Always use AVAX-USDC pool (already in checksum format from __init__)
            pool_address = self.pool_address
            logger.info(f"Fetching historical data for AVAX-USDC pool: {pool_address}")
            
            # Initialize pool contract with checksum address
            pool_contract = self.w3.eth.contract(
                address=pool_address,
                abi=self.pool_abi
            )
            print(f"\nInitialized contract for AVAX-USDC pool")
            
            # Get current block
            current_block = await self.w3.eth.block_number
            logger.info(f"Current block: {current_block}")
            
            # Calculate blocks for time windows (assuming 2s block time on Avalanche)
            blocks_per_day = 43200  # 86400 seconds / 2 seconds per block
            blocks_7d = blocks_per_day * 7
            blocks_30d = blocks_per_day * 30
            
            # Fetch historical data
            historical_data = await self._fetch_historical_data(
                pool_contract, 
                current_block,
                blocks_7d,
                blocks_30d
            )
            
            # Calculate metrics
            metrics = await self._calculate_metrics(historical_data)
            
            logger.info(f"Historical metrics calculated: {metrics}")

            # Store in cache before returning
            self._history_cache = metrics
            self._history_timestamp = now
            return metrics
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {str(e)}")
            raise Exception(f"Error fetching historical data: {str(e)}")
            
    async def _fetch_historical_data(self, contract, current_block: int, blocks_7d: int, blocks_30d: int) -> Dict:
        """Fetch historical data points"""
        try:
            # Get data points for different time windows
            data_7d = []
            data_30d = []
            
            # Sample blocks for 7d history
            for block in range(current_block - blocks_7d, current_block, blocks_7d // 24):
                active_id = await contract.functions.getActiveId().call(block_identifier=block)
                bin_data = await contract.functions.getBin(active_id).call(block_identifier=block)
                data_7d.append({
                    'block': block,
                    'active_id': active_id,
                    'reserves': bin_data
                })
                
            # Sample blocks for 30d history
            for block in range(current_block - blocks_30d, current_block, blocks_30d // 24):
                active_id = await contract.functions.getActiveId().call(block_identifier=block)
                bin_data = await contract.functions.getBin(active_id).call(block_identifier=block)
                data_30d.append({
                    'block': block,
                    'active_id': active_id,
                    'reserves': bin_data
                })
                
            return {
                '7d': data_7d,
                '30d': data_30d
            }
            
        except Exception as e:
            logger.error(f"Error fetching historical data points: {str(e)}")
            raise
            
    async def _calculate_metrics(self, historical_data: Dict) -> HistoricalMetrics:
        """Calculate metrics from historical data"""
        print(f"\nCalculating metrics from historical data: {historical_data}")
        try:
            # Calculate APRs
            apr_7d = self._calculate_apr(historical_data['7d'])
            apr_30d = self._calculate_apr(historical_data['30d'])
            
            # Calculate IL
            il_7d = self._calculate_impermanent_loss(historical_data['7d'])
            il_30d = self._calculate_impermanent_loss(historical_data['30d'])
            
            # Calculate volume trend
            volume_trend = self._calculate_volume_trend(historical_data['7d'])
            
            # Calculate price correlation and volatility
            price_data = self._extract_price_data(historical_data['30d'])
            volatility = self._calculate_volatility(price_data)
            correlation = self._calculate_price_correlation(price_data)
            
            # Calculate key price levels
            key_levels = self._identify_key_levels(price_data)
            
            return HistoricalMetrics(
                avg_apr_7d=apr_7d,
                avg_apr_30d=apr_30d,
                volume_trend=volume_trend,
                impermanent_loss_7d=il_7d,
                impermanent_loss_30d=il_30d,
                price_correlation=correlation,
                price_volatility=volatility,
                key_levels=key_levels
            )
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {str(e)}")
            raise

    def _calculate_apr(self, data_points: List[Dict]) -> float:
        """Calculate average APR from historical data points"""
        try:
            if not data_points:
                return 0.0

            # Calculate daily fee growth
            total_fees = 0
            for i in range(len(data_points) - 1):
                current = data_points[i]
                next_point = data_points[i + 1]
                
                # Calculate fee growth between points
                fee_growth = abs(
                    (float(next_point['reserves'][0]) - float(current['reserves'][0])) +
                    (float(next_point['reserves'][1]) - float(current['reserves'][1]))
                )
                total_fees += fee_growth

            # Calculate average daily fees
            days = len(data_points) / 24  # assuming 24 data points per day
            avg_daily_fees = total_fees / days if days > 0 else 0

            # Annualize
            annual_fees = avg_daily_fees * 365

            # Calculate APR (assuming total liquidity is average of first and last point)
            first_point_liq = float(data_points[0]['reserves'][0]) + float(data_points[0]['reserves'][1])
            last_point_liq = float(data_points[-1]['reserves'][0]) + float(data_points[-1]['reserves'][1])
            avg_liquidity = (first_point_liq + last_point_liq) / 2

            if avg_liquidity > 0:
                apr = (annual_fees / avg_liquidity) * 100
                return float(apr)
            return 0.0

        except Exception as e:
            logger.error(f"Error calculating APR: {str(e)}")
            return 0.0

    def _calculate_impermanent_loss(self, data_points: List[Dict]) -> float:
        """Calculate impermanent loss from price changes"""
        try:
            if not data_points:
                return 0.0

            # Get price at start and end (using reserves ratio)
            start_point = data_points[0]
            end_point = data_points[-1]

            # Calculate prices using reserve ratios
            start_price = float(start_point['reserves'][0]) / float(start_point['reserves'][1]) if float(start_point['reserves'][1]) > 0 else 0
            end_price = float(end_point['reserves'][0]) / float(end_point['reserves'][1]) if float(end_point['reserves'][1]) > 0 else 0

            if start_price == 0 or end_price == 0:
                return 0.0

            # Calculate price ratio
            price_ratio = end_price / start_price

            # IL formula: 2√(price_ratio)/(1+price_ratio) - 1
            il = 2 * np.sqrt(price_ratio) / (1 + price_ratio) - 1
            return float(abs(il) * 100)  # Return as percentage

        except Exception as e:
            logger.error(f"Error calculating IL: {str(e)}")
            return 0.0

    def _calculate_volume_trend(self, data_points: List[Dict]) -> Dict[str, Any]:
        """Calculate volume trend from historical data"""
        try:
            if not data_points:
                return {"trend": "stable", "change": 0.0}

            # Calculate daily volumes
            daily_volumes = []
            for i in range(len(data_points) - 1):
                current = data_points[i]
                next_point = data_points[i + 1]
                
                # Calculate volume between points
                volume = abs(
                    (float(next_point['reserves'][0]) - float(current['reserves'][0])) +
                    (float(next_point['reserves'][1]) - float(current['reserves'][1]))
                )
                daily_volumes.append(volume)

            if not daily_volumes:
                return {"trend": "stable", "change": 0.0}

            # Calculate trend
            avg_first_half = np.mean(daily_volumes[:len(daily_volumes)//2])
            avg_second_half = np.mean(daily_volumes[len(daily_volumes)//2:])
            
            if avg_first_half == 0:
                percent_change = 0.0
            else:
                percent_change = ((avg_second_half - avg_first_half) / avg_first_half) * 100

            # Determine trend direction
            if percent_change > 5:
                trend = "increasing"
            elif percent_change < -5:
                trend = "decreasing"
            else:
                trend = "stable"

            return {
                "trend": trend,
                "change": float(percent_change)
            }

        except Exception as e:
            logger.error(f"Error calculating volume trend: {str(e)}")
            return {"trend": "stable", "change": 0.0}

    def _calculate_price_correlation(self, price_data: List[float]) -> float:
        """Calculate price correlation with market"""
        # For now, return a placeholder value
        return 0.5

    def _calculate_volatility(self, price_data: List[float]) -> float:
        """Calculate price volatility"""
        try:
            if not price_data:
                return 0.0
            
            returns = np.diff(np.log(price_data))
            return float(np.std(returns) * np.sqrt(365))
        except Exception as e:
            logger.error(f"Error calculating volatility: {str(e)}")
            return 0.0

    def _identify_key_levels(self, price_data: List[float]) -> Dict[str, Decimal]:
        """Identify key price levels"""
        try:
            if not price_data:
                return {"support": Decimal('0'), "resistance": Decimal('0')}

            return {
                "support": Decimal(str(min(price_data))),
                "resistance": Decimal(str(max(price_data)))
            }
        except Exception as e:
            logger.error(f"Error identifying key levels: {str(e)}")
            return {"support": Decimal('0'), "resistance": Decimal('0')}

    def _extract_price_data(self, data_points: List[Dict]) -> List[float]:
        """Extract price data from historical data points"""
        try:
            prices = []
            for point in data_points:
                if float(point['reserves'][1]) > 0:
                    price = float(point['reserves'][0]) / float(point['reserves'][1])
                    prices.append(price)
            return prices
        except Exception as e:
            logger.error(f"Error extracting price data: {str(e)}")
            return []