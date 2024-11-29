import logging
from swarm import Agent, Swarm
from typing import Dict, Any, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)

class RouterAgent(Agent):
    def __init__(self):
        logger.info("="*50)
        logger.info("INITIALIZING ROUTER AGENT")
        logger.info("="*50)
        
        super().__init__(
            name="Router",
            model="gpt-4",
            instructions="""You are a routing assistant that determines the best agent to handle user requests.
            You must analyze messages and their context to determine if they are about:
            1. Token deployment (creating new tokens, deploying contracts)
            2. Image generation (creating logos, artwork, designs)
            3. Risk analysis (pool analysis, impermanent loss calculations)
            4. Liquidity Providing (LP) operations:
               - Questions about available pools
               - Adding/removing liquidity
               - Pool information
               - LP strategies
               - Must route to "trading" for any LP-related queries
            5. General crypto queries (prices, conversions, rates)
            
            IMPORTANT LP ROUTING RULES:
            - ANY question about pools, liquidity, or LP operations should go to "trading" agent
            - Examples of LP queries that should go to "trading":
              * "What pools are available?"
              * "Show me the pools"
              * "Where can I provide liquidity?"
              * "What are the LP options?"
            
            IMPORTANT: 
            - Users may write in any language
            - Consider the entire conversation context, not just the latest message
            - More recent messages have higher priority
            - Look for continuity in conversations (e.g., providing token parameters)
            
            ALWAYS use the determine_agent function to specify which agent should handle the request.
            DO NOT provide additional explanations, ONLY use the function.""",
            functions=[self.determine_agent]
        )

    async def determine_agent(self, agent_type: str = "base", confidence: float = 0.5, reasoning: str = "") -> Dict[str, Any]:
        """Determine which agent should handle the request
        
        Args:
            agent_type: The type of agent (deployment, image, risk, trading, base)
            confidence: Confidence level in the routing decision (0-1)
            reasoning: Explanation of why this agent was chosen
        """
        return {
            "agent_type": agent_type,
            "confidence": confidence,
            "reasoning": reasoning
        }

    async def analyze_intent(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Analyze message intent and context to route to appropriate agent"""
        try:
            client = Swarm()
            print(context, "context check dude context man inside router")
            # Format context for analysis - Reverse the order to prioritize recent messages
            context_messages = []
            if context:
                # Convert context items to list and reverse them
                context_items = list(context.items())
                context_items.reverse()
                
                for role, text in context_items:
                    if isinstance(text, str):
                        context_messages.append(f"{role}: {text}")
                    elif isinstance(text, dict):
                        context_messages.append(f"{role}: {text.get('message', str(text))}")

            # Create conversation history string
            conversation = "\n".join(context_messages) if context_messages else ""
            
            # Add context to the messages
            messages = [{"role": "user", "content": f"""Analyze this conversation and determine the best agent to handle it:

Previous conversation (most recent first):
{conversation}

Current message:
{message}"""}]

            response = client.run(
                agent=self,
                messages=messages,
                context_variables=context
            )
                        # Extract the function call response
            tool_calls = response.messages[0].get('tool_calls', [])
            if tool_calls:
                import json
                return json.loads(tool_calls[0]['function']['arguments'])
            # Fallback response if no function call
            else: return {
                "agent_type": "base",
                "confidence": 0.5,
                "reasoning": "Failed to determine specific intent"
            }

        except Exception as e:
            logger.error(f"Error analyzing message intent: {str(e)}")
            return {
                "agent_type": "base",
                "confidence": 0,
                "reasoning": f"Error: {str(e)}"
            } 