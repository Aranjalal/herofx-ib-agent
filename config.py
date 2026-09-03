"""
Configuration management for HeroFX IB Agent
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
POSTED_DB_FILE = BASE_DIR / "posted.json"

class Config:
    def __init__(self):
        self._data = self._load()
    
    def _load(self) -> Dict[str, Any]:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def reload(self):
        self._data = self._load()
    
    def get(self, key: str, default=None):
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default
    
    @property
    def admin_id(self) -> int:
        return self._data["admin"]["telegram_user_id"]
    
    @property
    def instagram_username(self) -> str:
        return self._data["instagram"]["username"]
    
    @property
    def check_interval_hours(self) -> int:
        return self._data["instagram"]["check_interval_hours"]
    
    @property
    def ib_url(self) -> str:
        return self._data["ib_link"]["url"]
    
    @property
    def posting_time(self) -> str:
        return self._data["settings"]["posting_time"]
    
    @property
    def timezone(self) -> str:
        return self._data["settings"]["timezone"]
    
    @property
    def ai_model(self) -> str:
        return self._data["ai"]["model"]
    
    @property
    def ai_max_tokens(self) -> int:
        return self._data["ai"]["max_tokens"]
    
    @property
    def ai_temperature(self) -> float:
        return self._data["ai"]["temperature"]
    
    @property
    def max_caption_length(self) -> int:
        return self._data["settings"]["max_caption_length"]
    
    @property
    def delay_between_posts(self) -> int:
        return self._data["settings"]["delay_between_posts_seconds"]
    
    def get_channel(self, channel_key: str) -> Dict[str, Any]:
        return self._data["telegram"][channel_key]
    
    def get_ib_footer(self, caption: str, lang: str) -> str:
        """Get IB footer based on caption topic detection."""
        text_lower = (caption or "").lower()
        keywords = self._data["ib_link"]["keywords"]
        templates = self._data["ib_link"]["cta_templates"]
        
        for category, words in keywords.items():
            for word in words:
                if word in text_lower:
                    if category in templates and lang in templates[category]:
                        return f"\n\n{templates[category][lang]}"
        
        if "general" in templates and lang in templates["general"]:
            return f"\n\n{templates['general'][lang]}"
        return ""


class PostedDB:
    def __init__(self):
        self.file = POSTED_DB_FILE
        self.data = self._load()
    
    def _load(self) -> Dict[str, Any]:
        if self.file.exists():
            with open(self.file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"posted_ids": [], "pending": {}}
    
    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def is_posted(self, post_id: str) -> bool:
        return post_id in self.data["posted_ids"]
    
    def mark_posted(self, post_id: str):
        if post_id not in self.data["posted_ids"]:
            self.data["posted_ids"].append(post_id)
            self.save()
    
    def add_pending(self, post_id: str, data: Dict[str, Any]):
        self.data["pending"][post_id] = data
        self.save()
    
    def get_pending(self, post_id: str) -> Dict[str, Any]:
        return self.data["pending"].get(post_id)
    
    def remove_pending(self, post_id:str):
        if post_id in self.data["pending"]:
            del self.data["pending"][post_id]
            self.save()
    
    @property
    def pending_count(self) -> int:
        return len(self.data["pending"])
