import logging
from swarm import Agent
from typing import Dict, Any, Optional
from django.conf import settings
from pydantic import Field, ConfigDict
from swarm import Swarm

logger = logging.getLogger(__name__)

class DeploymentAgent(Agent):
    def __init__(self):
        logger.info("="*50)
        logger.info("INITIALIZING DEPLOYMENT AGENT")
        logger.info("="*50)
        
        super().__init__(
            name="Deployment Assistant",
            model="gpt-4",
            instructions="""You are a deployment assistant that helps users deploy ERC-20 tokens through natural conversation.
            
            Your task is to analyze messages and context to identify token deployment parameters:
            1. name: The token's full name
            2. symbol: The token's ticker symbol (usually 3-4 characters)
            3. total_supply: The total supply of tokens (default: 1,000,000)
            4. logo: A token logo image is required before deployment
            
            IMPORTANT:
            - Users may write in any language
            - CAREFULLY analyze the entire conversation history to find previously provided parameters
            - Do not ask for information that was already provided in the conversation
            - When all parameters (name, symbol, supply, logo) are found in the context, proceed with deployment
            - If user asks to deploy and all parameters are present, use prepare_token_deployment
            - Only ask for missing parameters that haven't been mentioned in the conversation
            
            ALWAYS use the extract_token_parameters function to specify found parameters.
            Include reasoning about why you identified each parameter.""",
            functions=[self.extract_token_parameters, self.prepare_token_deployment]
        )

    async def extract_token_parameters(
        self,
        name: Optional[str] = None,
        symbol: Optional[str] = None,
        total_supply: Optional[int] = None,
        logo_url: Optional[str] = None,
        reasoning: str = ""
    ) -> Dict[str, Any]:
        """Extract token parameters from message and context
        
        Args:
            name: Token name if found
            symbol: Token symbol if found
            total_supply: Total supply if found
            logo_url: URL of the token logo if found
            reasoning: Explanation of parameter extraction
        """
        return {
            "parameters": {
                "name": name,
                "symbol": symbol,
                "total_supply": total_supply,
                "logo_url": logo_url
            },
            "reasoning": reasoning
        }

    async def process_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Process deployment requests using Swarm's AI capabilities"""
        try:
            # Initialize context variables
            context_variables = context or {}
            deployment_params = {}
            
            # Get conversation history
            conversation_history = context_variables.get('history', [])
            
            # Process conversation history
            formatted_history = []
            for item in conversation_history:
                role = item.get('role')
                content = item.get('content')
                
                if content.startswith('http') and ('png' in content or 'jpg' in content):
                    deployment_params["logo_url"] = content
                    formatted_history.append(f"{role}: <image_url>")
                else:
                    formatted_history.append(f"{role}: {content}")

            # Build the full conversation context
            full_conversation = "\n".join(formatted_history)
            
            logger.info(f"Processing full conversation:\n{full_conversation}")
            
            # Analyze message and context with AI
            client = Swarm()
            response = client.run(
                agent=self,
                messages=[{
                "role": "system",
                "content": "You are analyzing a conversation to extract token deployment parameters. The conversation history is provided in chronological order."
            }, {
                "role": "user",
                "content": f"""Previous conversation:
{full_conversation}

Current message:
{message}"""
                }]
            )

            # Extract parameters from AI response
            tool_calls = response.messages[0].get('tool_calls', [])
            if tool_calls and tool_calls[0]['type'] == 'function':
                try:
                    import json
                    args = json.loads(tool_calls[0]['function']['arguments'])
                    
                    # Update deployment params with all found parameters
                    if args.get("name"):
                        deployment_params["name"] = args["name"]
                    if args.get("symbol"):
                        deployment_params["symbol"] = args["symbol"]
                    if args.get("total_supply"):
                        deployment_params["total_supply"] = int(args["total_supply"])

                    # If we have all required parameters, proceed with deployment
                    if all(key in deployment_params for key in ["name", "symbol", "logo_url"]):
                        return await self.prepare_token_deployment(
                            name=deployment_params["name"],
                            symbol=deployment_params["symbol"],
                            total_supply=deployment_params.get("total_supply", 1_000_000),
                            logo_url=deployment_params["logo_url"]
                        )

                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing AI response: {str(e)}")
                    return {"error": "Invalid response format from AI"}

            # If we get here, something is missing
            return await self.generate_next_prompt(deployment_params)

        except Exception as e:
            logger.error(f"Error processing deployment message: {str(e)}")
            return {"error": str(e)}

    async def generate_next_prompt(self, collected_params: Dict[str, Any]) -> str:
        """Generate appropriate next message based on missing parameters"""
        client = Swarm()
        response = client.run(
            agent=self,
            messages=[{
                "role": "system",
                "content": f"""Current parameters: {collected_params}
                Generate a natural response asking for missing required parameters (name, symbol, total_supply).
                If all parameters are collected, ask for confirmation."""
            }]
        )
        return response.messages[-1]["content"]

    async def prepare_token_deployment(self, 
        name: str,
        symbol: str,
        total_supply: int = 1_000_000,
        decimals: int = 18,
        logo_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Prepare ERC-20 token deployment data for frontend"""
        try:
            client = Swarm()
            
            # Check if we have a logo
            if not logo_url:
                return {
                    "type": "needs_image",
                    "message": f"Great! I have all the token details. Now we just need a logo for your {name} token. Would you like me to generate one for you?",
                    "deployment_params": {
                        "name": name,
                        "symbol": symbol,
                        "total_supply": total_supply
                    }
                }
            
            # Let AI generate the confirmation message
            response = client.run(
                agent=self,
                messages=[{
                    "role": "system", 
                    "content": "Generate a friendly confirmation message for token deployment. Include all parameters and ask for confirmation."
                }, {
                    "role": "user",
                    "content": f"Generate deployment confirmation for: Name={name}, Symbol={symbol}, Total Supply={total_supply}, Decimals={decimals}, Logo=Yes"
                }]
            )
            
            ai_message = response.messages[-1]["content"]
            
            return {
                "type": "deployment_ready",
                "network": {
                    "name": "unichain",
                    "rpc_url": "https://sepolia.unichain.org",
                    "chain_id": "222"
                },
                "contract_data": {
                    "abi": [
                        {
                            "inputs": [],
                            "stateMutability": "nonpayable",
                            "type": "constructor"
                        },
                        {
                            "inputs": [
                                {
                                    "internalType": "string",
                                    "name": "_name",
                                    "type": "string"
                                },
                                {
                                    "internalType": "string",
                                    "name": "_symbol",
                                    "type": "string"
                                },
                                {
                                    "internalType": "uint8",
                                    "name": "_decimals",
                                    "type": "uint8"
                                }
                            ],
                            "stateMutability": "nonpayable",
                            "type": "constructor"
                        }
                    ],
                    "bytecode": "0x60806040523480156200001157600080fd5b506040518060400160405280600b81526020016a45786..."
                },
                "constructor_args": [name, symbol, decimals],
                "deployment_params": {
                    "name": name,
                    "symbol": symbol,
                    "decimals": decimals,
                    "total_supply": total_supply,
                    "logo_url": logo_url
                },
                "message": ai_message
            }
        except Exception as e:
            logger.error(f"Error preparing token deployment: {str(e)}")
            return {"error": str(e)}