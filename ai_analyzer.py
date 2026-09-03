"""
AI Analyzer - Uses Gemini to understand Instagram posts and generate captions
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class AIAnalyzer:
    def __init__(self, api_key: str, model: str = "gemini-3.5-flash-lite", 
                 max_tokens: int = 1024, temperature: float = 0.7):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
    
    def analyze_post(self, image_paths: List[Path], original_caption: str) -> Optional[Dict[str, str]]:
        """
        Analyze an Instagram post and generate Kurdish Sorani + Arabic captions.
        
        Returns:
            Dict with 'ckb' and 'ar' captions, or None if analysis fails.
        """
        if not image_paths:
            logger.error("No images provided for analysis")
            return None
        
        # Build the prompt
        prompt = self._build_prompt(original_caption)
        
        # Build content parts
        parts = [prompt]
        
        for img_path in image_paths:
            if img_path and img_path.exists():
                with open(img_path, "rb") as f:
                    image_data = f.read()
                ext = img_path.suffix.lower()
                mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                parts.append(types.Part.from_bytes(data=image_data, mime_type=mime))
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=parts,
                config=types.GenerateContentConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature
                )
            )
            
            text = response.text
            logger.info(f"AI response received: {len(text)} chars")
            
            # Parse the response
            ckb_match = re.search(r'KURDISH_SORANI:\s*\n(.*?)(?=\nARABIC:|\Z)', text, re.DOTALL)
            ar_match = re.search(r'ARABIC:\s*\n(.*?)(?=\Z)', text, re.DOTALL)
            
            ckb_text = self._clean_text(ckb_match.group(1).strip()) if ckb_match else ""
            ar_text = self._clean_text(ar_match.group(1).strip()) if ar_match else ""
            
            if not ckb_text and not ar_text:
                logger.warning("AI returned empty captions")
                return None
            
            return {
                "ckb": ckb_text,
                "ar": ar_text
            }
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return None
    
    def _build_prompt(self, original_caption: str) -> str:
        """Build the prompt for the AI."""
        return f"""You are a professional social media manager and Introducing Broker (IB) for HeroFX, a forex and CFD trading broker. Your job is to analyze Instagram posts and create engaging captions for two different audiences.

YOUR AUDIENCES:
1. Kurdish Sorani speakers (Iraqi Kurdistan region) - for PalawanFX Telegram channel
2. Arabic speakers (Modern Standard Arabic) - for BatalFX Telegram channel

YOUR CONTEXT AS AN IB:
- You earn commissions when people sign up and trade through your link
- HeroFX offers: Raw spreads from -0.4 pips, 100% deposit bonus, Hero10X insta-funded accounts
- You earn up to $10 per lot traded (direct clients), with multi-level commissions
- Daily commission payouts, fast withdrawals, 24/7 support

YOUR TASK:
1. Look at EACH image carefully - read ALL text visible on the images
2. Read the original Instagram caption below
3. COMBINE the visual information AND the caption to understand the full message
4. Write TWO new captions that:
   - Capture the COMPLETE message (from both images AND caption)
   - Sound like a native speaker wrote them (NOT translated - naturally written)
   - Are engaging and suitable for Telegram channels
   - Include relevant emojis naturally
   - Are written from the perspective of an IB who wants to help their audience benefit
   - Do NOT include the IB link (that will be added separately)

IMPORTANT RULES:
- Kurdish Sorani: Use Sorani dialect (Iraqi Kurdish), NOT Kurmanji. Use Arabic script.
- Arabic: Use Modern Standard Arabic (MSA), NOT dialect. Formal but engaging.
- Do NOT just translate - REWRITE for each audience naturally
- Keep the tone professional but friendly
- If the post is about trading education, make it educational
- If the post is about promotions/bonuses, make it exciting
- If the post is about market analysis, make it insightful

ORIGINAL INSTAGRAM CAPTION:
{original_caption or "No caption provided"}

RESPOND IN THIS EXACT FORMAT (do not add any other text):
KURDISH_SORANI:
[your Kurdish Sorani caption here]

ARABIC:
[your Arabic caption here]"""
    
    def _clean_text(self, text: str) -> str:
        """Clean up AI-generated text."""
        if not text:
            return ""
        # Remove unwanted characters
        text = text.replace("\u2728", "").replace("\U0001F4CC", "")
        text = text.replace("\U0001F449", "").replace("\U0001F448", "")
        text = text.replace("\u200c", "").strip()
        return text.strip().strip('"').strip("'")
