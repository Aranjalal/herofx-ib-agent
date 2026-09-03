"""
Instagram Monitor - checks @herofx_official for new posts
Uses Playwright to read the page like a human
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger(__name__)

TEMP_DIR = Path(__file__).parent / "temp"
TEMP_DIR.mkdir(exist_ok=True)


class InstagramPost:
    def __init__(self, shortcode: str, url: str, caption: str, 
                 media_urls: List[str], media_types: List[str]):
        self.shortcode = shortcode
        self.url = url
        self.caption = caption
        self.media_urls = media_urls
        self.media_types = media_types  # "image" or "video"
    
    @property
    def post_id(self) -> str:
        return self.shortcode
    
    def __repr__(self):
        return f"InstagramPost({self.shortcode}, {len(self.media_urls)} media)"


class InstagramMonitor:
    def __init__(self, username: str):
        self.username = username
        self.base_url = f"https://www.instagram.com/{username}/"
    
    async def check_new_posts(self, last_shortcode: Optional[str] = None) -> List[InstagramPost]:
        """Check for new posts. Returns posts newer than last_shortcode."""
        posts = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()
            
            try:
                logger.info(f"Navigating to {self.base_url}")
                await page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)
                
                # Close login popup if it appears
                await self._close_login_popup(page)
                
                # Get all post links from the page
                post_links = await self._get_post_links(page)
                logger.info(f"Found {len(post_links)} post links")
                
                for link in post_links[:12]:  # Check last 12 posts
                    shortcode = self._extract_shortcode(link)
                    if not shortcode:
                        continue
                    
                    if last_shortcode and shortcode == last_shortcode:
                        break  # Reached the last processed post
                    
                    if not last_shortcode or shortcode != last_shortcode:
                        # New post found
                        post = await self._get_post_details(page, shortcode)
                        if post:
                            posts.append(post)
                
            except Exception as e:
                logger.error(f"Instagram check failed: {e}")
            finally:
                await browser.close()
        
        return posts
    
    async def get_post_by_url(self, url: str) -> Optional[InstagramPost]:
        """Get a specific post by URL (for on-demand mode)."""
        shortcode = self._extract_shortcode(url)
        if not shortcode:
            return None
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()
            
            try:
                post = await self._get_post_details(page, shortcode)
                return post
            except Exception as e:
                logger.error(f"Failed to get post {shortcode}: {e}")
                return None
            finally:
                await browser.close()
    
    async def _close_login_popup(self, page: Page):
        """Close the login popup if it appears."""
        try:
            # Try multiple selectors for the close button
            selectors = [
                'button[type="button"]',
                'button._ac8f',
                'button[aria-label="Close"]',
                'svg[aria-label="Close"]',
                'button:has-text("Not Now")',
                'button:has-text("Not now")',
                'a:has-text("Not Now")',
            ]
            
            for selector in selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(1)
                        logger.info("Closed login popup")
                        return
                except:
                    continue
            
            # Try pressing Escape
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.debug(f"Popup close error: {e}")
    
    async def _get_post_links(self, page: Page) -> List[str]:
        """Extract post links from profile page."""
        links = []
        
        # Scroll down to load more posts
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1)
        
        # Find all links matching /p/ pattern
        all_links = await page.query_selector_all('a[href*="/p/"]')
        for link in all_links:
            href = await link.get_attribute("href")
            if href and href not in links:
                # Make sure it's a post link, not a profile link
                if re.search(r'/p/[A-Za-z0-9_-]+', href):
                    links.append(href)
        
        return links
    
    async def _get_post_details(self, page: Page, shortcode: str) -> Optional[InstagramPost]:
        """Navigate to a post and extract its details."""
        post_url = f"https://www.instagram.com/p/{shortcode}/"
        
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            # Close popup if needed
            await self._close_login_popup(page)
            
            # Extract caption
            caption = await self._extract_caption(page)
            
            # Extract media (images and videos)
            media_urls, media_types = await self._extract_media(page)
            
            if not media_urls:
                logger.warning(f"No media found for {shortcode}")
                return None
            
            return InstagramPost(
                shortcode=shortcode,
                url=post_url,
                caption=caption,
                media_urls=media_urls,
                media_types=media_types
            )
            
        except Exception as e:
            logger.error(f"Error getting post details for {shortcode}: {e}")
            return None
    
    async def _extract_caption(self, page: Page) -> str:
        """Extract caption text from a post."""
        caption = ""
        
        try:
            # Try to find caption in various places
            # Method 1: Look for article div with text
            article = await page.query_selector('article')
            if article:
                # Get all text spans in the article
                spans = await article.query_selector_all('span')
                for span in spans:
                    text = await span.inner_text()
                    if text and len(text) > 15 and not text.startswith("Photo by") and not text.startswith("Video by"):
                        caption = text
                        break
            
            # Method 2: Look for specific caption selectors
            if not caption:
                selectors = [
                    'h1._aacl',
                    'div._a9zs span',
                    'article div span',
                    '[role="dialog"] span',
                    'header + div span',
                    'div._a9zr span',
                ]
                
                for selector in selectors:
                    elements = await page.query_selector_all(selector)
                    for el in elements:
                        text = await el.inner_text()
                        if text and len(text) > 15:
                            caption = text
                            break
                    if caption:
                        break
            
        except Exception as e:
            logger.debug(f"Caption extraction error: {e}")
        
        return caption or ""
    
    async def _extract_media(self, page: Page) -> tuple[List[str], List[str]]:
        """Extract image and video URLs from a post."""
        media_urls = []
        media_types = []
        
        try:
            # Get all images in the article/post area
            img_elements = await page.query_selector_all('article img[src]')
            
            for img in img_elements:
                src = await img.get_attribute("src")
                alt = await img.get_attribute("alt") or ""
                cls = await img.get_attribute("class") or ""
                
                # Skip profile pictures and small icons
                if "profile" in cls.lower():
                    continue
                if "profile" in alt.lower():
                    continue
                
                # Skip if it's a small icon or emoji
                if any(skip in src for skip in ["emoji", "icon", "profile"]):
                    continue
                
                # Check if it's a post image (has fbcdn in URL)
                if ("fbcdn" in src or "instagram.com" in src) and src not in media_urls:
                    # Check if it's a video thumbnail
                    if "Video" in alt or "Video" in cls:
                        media_urls.append(src)
                        media_types.append("video")
                    else:
                        media_urls.append(src)
                        media_types.append("image")
            
            # Also check for video elements
            video_elements = await page.query_selector_all('article video')
            for vid in video_elements:
                src = await vid.get_attribute("src")
                if src and src not in media_urls:
                    media_urls.append(src)
                    media_types.append("video")
            
            # If no images found in article, try broader search
            if not media_urls:
                all_imgs = await page.query_selector_all('img[src*="fbcdn"]')
                for img in all_imgs:
                    src = await img.get_attribute("src")
                    alt = await img.get_attribute("alt") or ""
                    if "profile" not in alt.lower() and src not in media_urls:
                        media_urls.append(src)
                        media_types.append("image")
                        
        except Exception as e:
            logger.debug(f"Media extraction error: {e}")
        
        return media_urls, media_types
    
    def _extract_shortcode(self, url: str) -> Optional[str]:
        """Extract shortcode from Instagram URL."""
        match = re.search(r'/p/([A-Za-z0-9_-]+)', url)
        return match.group(1) if match else None
    
    async def download_media(self, post: InstagramPost) -> List[Path]:
        """Download media files from a post."""
        paths = []
        
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            for i, (url, mtype) in enumerate(zip(post.media_urls, post.media_types)):
                try:
                    ext = "mp4" if mtype == "video" else "jpg"
                    filename = f"{post.shortcode}_{i}.{ext}"
                    filepath = TEMP_DIR / filename
                    
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            with open(filepath, "wb") as f:
                                f.write(await resp.read())
                            paths.append(filepath)
                            logger.info(f"Downloaded: {filename}")
                except Exception as e:
                    logger.error(f"Download error: {e}")
        
        return paths
