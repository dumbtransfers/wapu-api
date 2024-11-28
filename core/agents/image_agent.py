import logging
from openai import OpenAI
from swarm import Agent
from typing import Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

class ImageAgent(Agent):
    def __init__(self):
        logger.info("="*50)
        logger.info("INITIALIZING IMAGE GENERATION AGENT")
        logger.info("="*50)
        
        super().__init__(
            name="Sofia Image Assistant",
            model="gpt-4",
            instructions="""You are an image generation assistant that helps users create images for their tokens.""",
            functions=[self.generate_image]
        )

    async def generate_image(self, prompt: str) -> Dict[str, Any]:
        """Generate image using DALL-E 3"""
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )

            return {
                "type": "image_ready",
                "image_data": {
                    "url": response.data[0].url,
                    "revised_prompt": response.data[0].revised_prompt
                },
                "prompt": prompt,
                "message": "I've generated your image! Would you like to use this for a token?"
            }
            
        except Exception as e:
            logger.error(f"Error generating image: {str(e)}")
            return {"error": str(e)}

    async def process_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Process image generation requests"""
        try:
            # Check if this is a follow-up to token creation
            if context and context.get('deployment_params'):
                # Use token details to enhance the prompt
                token_name = context['deployment_params'].get('name', '')
                token_symbol = context['deployment_params'].get('symbol', '')
                
                # Create a more detailed prompt using token info
                base_prompt = message.strip()
                if token_name and token_symbol:
                    prompt = f"{base_prompt} for a cryptocurrency token named {token_name} ({token_symbol}). Make it suitable as a token logo."
                elif token_name:
                    prompt = f"{base_prompt} for a cryptocurrency token named {token_name}. Make it suitable as a token logo."
                else:
                    prompt = f"{base_prompt}. Make it suitable as a token logo."
            else:
                prompt = message

            return await self.generate_image(prompt)

        except Exception as e:
            logger.error(f"Error processing image message: {str(e)}")
            return {"error": str(e)} 