import os
import time
import json
from typing import List, Optional, Dict, Any
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
import google.generativeai as genai
from pathlib import Path
import logging
from dotenv import load_dotenv
import base64
import hashlib
import re
from PIL import Image

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Enhanced system prompt for better task completion
SYSTEM_PROMPT = """You are an expert web testing automation assistant. Your primary goal is to complete the given task efficiently and provide clear results.

Available actions:
1. "javascript" - Execute JavaScript code to interact with the page
2. "wait" - Wait for page elements to load or change (1-5 seconds)
3. "end" - End the test with analysis report when task is complete

JavaScript Helper Functions Available:
- quickClick(selector) - Click an element
- quickFill(selector, value) - Fill input field
- quickSubmit(formSelector) - Submit a form
- findElements(selector) - Find elements on page
- scrollToElement(selector) - Scroll to element
- getCurrentInfo() - Get current page info

Guidelines for SUCCESS:
- Be decisive and focused on the main task
- Use specific CSS selectors (prefer id, class, data attributes)
- Check if task is completed after each action
- If you find the information or complete the goal, immediately use "end" action
- Handle popups, cookies banners, and modals first
- Use wait action when page is loading or changing
- Provide detailed analysis when ending

Response must be valid JSON with "action" field and appropriate additional fields.

CRITICAL: End the test immediately when the main objective is achieved or sufficient information is gathered."""

class EnhancedWebTestingAutomation:
    def __init__(self, gemini_api_key: str, chrome_driver_path: Optional[str] = None):
        """Initialize the Enhanced Web Testing Automation system."""
        try:
            # Configure Gemini with better error handling
            genai.configure(api_key=gemini_api_key)
            self.model = genai.GenerativeModel(
                'gemini-1.5-pro',
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Lower temperature for more consistent responses
                    max_output_tokens=2048
                )
            )
            
            self.driver = None
            self.wait = None
            self.conversation_history = []
            self.screenshot_count = 0
            self.screenshots_dir = Path("test_screenshots")
            self.screenshots_dir.mkdir(exist_ok=True)
            self.chrome_driver_path = chrome_driver_path
            
            # Enhanced optimization flags
            self.page_state_cache = {}
            self.last_page_hash = None
            self.consecutive_same_state_count = 0
            self.max_same_state_count = 2  # Reduced for faster detection
            self.successful_actions = 0
            self.failed_actions = 0
            self.start_time = time.time()
            
            logger.info("Enhanced Web Testing Automation initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize automation: {e}")
            raise
        
    def setup_selenium(self, headless: bool = False) -> bool:
        """Set up Selenium WebDriver with enhanced options and error handling."""
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless=new")  # Use new headless mode
            
            # Enhanced Chrome options for stability and speed
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--disable-features=TranslateUI")
            chrome_options.add_argument("--disable-ipc-flooding-protection")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--no-service-autorun")
            chrome_options.add_argument("--password-store=basic")
            chrome_options.add_argument("--use-mock-keychain")
            chrome_options.add_argument("--disable-background-networking")
            chrome_options.add_argument("--disable-default-apps")
            chrome_options.add_argument("--disable-sync")
            chrome_options.add_argument("--metrics-recording-only")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--no-pings")
            chrome_options.add_argument("--disable-notifications")
            
            # Performance optimizations
            chrome_options.add_argument("--aggressive-cache-discard")
            chrome_options.add_argument("--memory-pressure-off")
            
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Enhanced preferences
            prefs = {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_settings.popups": 0,
                "profile.managed_default_content_settings.images": 1,  # Allow images for better analysis
                "profile.default_content_setting_values.plugins": 1,
                "profile.default_content_setting_values.geolocation": 2,
                "profile.default_content_setting_values.media_stream": 2,
                "profile.managed_default_content_settings.media_stream": 2
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
            # Try different Chrome driver initialization methods
            try:
                if self.chrome_driver_path and os.path.exists(self.chrome_driver_path):
                    service = Service(self.chrome_driver_path)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                else:
                    # Try to use system Chrome driver
                    self.driver = webdriver.Chrome(options=chrome_options)
                    
            except Exception as e:
                logger.warning(f"Failed with Chrome driver path, trying system driver: {e}")
                self.driver = webdriver.Chrome(options=chrome_options)
            
            # Configure timeouts and window
            self.driver.implicitly_wait(3)
            self.driver.set_page_load_timeout(30)
            self.driver.set_script_timeout(15)
            self.driver.set_window_size(1366, 768)
            
            # Create WebDriverWait instance
            self.wait = WebDriverWait(self.driver, 10)
            
            # Add stealth properties
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("Selenium WebDriver initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            return False
    
    def take_screenshot_optimized(self) -> str:
        """Take an optimized screenshot with compression."""
        try:
            screenshot_path = self.screenshots_dir / f"screenshot_{self.screenshot_count:04d}.png"
            
            # Take screenshot
            if not self.driver.save_screenshot(str(screenshot_path)):
                logger.error("Failed to save screenshot")
                return ""
            
            # Optimize image size for faster API calls
            try:
                with Image.open(screenshot_path) as img:
                    # Resize if too large
                    if img.width > 1280 or img.height > 720:
                        img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
                        img.save(screenshot_path, optimize=True, quality=85)
            except Exception as e:
                logger.warning(f"Image optimization failed: {e}")
            
            self.screenshot_count += 1
            logger.info(f"Screenshot saved: {screenshot_path}")
            return str(screenshot_path)
            
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return ""
    
    def get_enhanced_page_info(self) -> Dict[str, Any]:
        """Get comprehensive page information with error handling."""
        try:
            page_info = {
                "url": self.driver.current_url,
                "title": self.driver.title,
                "page_source_length": len(self.driver.page_source),
                "interactive_elements": [],
                "page_status": "loaded"
            }
            
            # Check if page is still loading
            try:
                ready_state = self.driver.execute_script("return document.readyState")
                page_info["ready_state"] = ready_state
                if ready_state != "complete":
                    page_info["page_status"] = "loading"
            except:
                pass
            
            # Get interactive elements with better error handling
            selectors_map = {
                "input": "input:not([type='hidden'])",
                "button": "button, input[type='button'], input[type='submit']",
                "select": "select",
                "textarea": "textarea",
                "link": "a[href]:not([href='#']):not([href^='javascript:'])",
                "form": "form"
            }
            
            for element_type, selector in selectors_map.items():
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)[:8]  # Limit elements
                    
                    for i, elem in enumerate(elements):
                        try:
                            # Check if element is visible
                            if not elem.is_displayed():
                                continue
                            
                            elem_info = {
                                "type": element_type,
                                "index": i,
                                "tag": elem.tag_name,
                                "id": elem.get_attribute("id") or "",
                                "class": elem.get_attribute("class") or "",
                                "text": (elem.text or "").strip()[:100],
                                "visible": elem.is_displayed(),
                                "enabled": elem.is_enabled()
                            }
                            
                            # Add specific attributes
                            if element_type == "input":
                                elem_info.update({
                                    "input_type": elem.get_attribute("type") or "text",
                                    "name": elem.get_attribute("name") or "",
                                    "placeholder": elem.get_attribute("placeholder") or "",
                                    "value": elem.get_attribute("value") or ""
                                })
                            elif element_type == "link":
                                href = elem.get_attribute("href") or ""
                                elem_info["href"] = href[:100]  # Truncate long URLs
                            elif element_type == "form":
                                elem_info.update({
                                    "action": elem.get_attribute("action") or "",
                                    "method": (elem.get_attribute("method") or "GET").upper()
                                })
                            elif element_type == "button":
                                elem_info["onclick"] = elem.get_attribute("onclick") or ""
                            
                            page_info["interactive_elements"].append(elem_info)
                            
                        except Exception as e:
                            logger.debug(f"Error processing element {i}: {e}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"Error finding {element_type} elements: {e}")
                    continue
            
            # Get any error messages or alerts
            try:
                alerts = self.driver.find_elements(By.CSS_SELECTOR, ".alert, .error, .warning, [role='alert']")
                if alerts:
                    page_info["alerts"] = [alert.text.strip()[:200] for alert in alerts[:3] if alert.is_displayed()]
            except:
                pass
            
            return page_info
            
        except Exception as e:
            logger.error(f"Failed to get page info: {e}")
            return {
                "url": getattr(self.driver, 'current_url', 'unknown'),
                "title": "Error getting page info",
                "interactive_elements": [],
                "error": str(e)
            }
    
    def get_page_state_hash(self) -> str:
        """Generate a more comprehensive hash of the current page state."""
        try:
            url = self.driver.current_url
            title = self.driver.title
            
            # Get content indicators
            try:
                content_length = len(self.driver.page_source)
                forms_count = len(self.driver.find_elements(By.TAG_NAME, "form"))
                inputs_count = len(self.driver.find_elements(By.CSS_SELECTOR, "input:not([type='hidden'])"))
                buttons_count = len(self.driver.find_elements(By.CSS_SELECTOR, "button, input[type='button'], input[type='submit']"))
                links_count = len(self.driver.find_elements(By.CSS_SELECTOR, "a[href]"))
                
                # Get page ready state
                ready_state = self.driver.execute_script("return document.readyState")
                
                state_string = f"{url}|{title}|{content_length}|{forms_count}|{inputs_count}|{buttons_count}|{links_count}|{ready_state}"
                return hashlib.md5(state_string.encode()).hexdigest()
                
            except Exception as e:
                # Fallback hash
                return hashlib.md5(f"{url}|{title}".encode()).hexdigest()
                
        except Exception as e:
            logger.error(f"Error generating page hash: {e}")
            return str(time.time())  # Fallback to timestamp
    
    def execute_javascript_enhanced(self, js_code: str) -> tuple[bool, str]:
        """Execute JavaScript with enhanced error handling and helper functions."""
        try:
            # Enhanced JavaScript wrapper with more helper functions
            enhanced_js = f"""
            try {{
                // Helper functions
                function quickClick(selector) {{
                    const elements = typeof selector === 'string' ? document.querySelectorAll(selector) : [selector];
                    for (let el of elements) {{
                        if (el && el.offsetParent !== null) {{ // Check if visible
                            el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                            setTimeout(() => {{
                                el.click();
                            }}, 100);
                            return 'Clicked element: ' + (el.id || el.className || el.tagName);
                        }}
                    }}
                    throw new Error('No visible element found for: ' + selector);
                }}
                
                function quickFill(selector, value) {{
                    const el = document.querySelector(selector);
                    if (!el) throw new Error('Input not found: ' + selector);
                    
                    el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    el.focus();
                    
                    // Clear existing value
                    el.value = '';
                    
                    // Set new value
                    el.value = value;
                    
                    // Trigger events
                    el.dispatchEvent(new Event('input', {{bubbles: true, cancelable: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true, cancelable: true}}));
                    el.dispatchEvent(new Event('keyup', {{bubbles: true, cancelable: true}}));
                    
                    return 'Filled input: ' + (el.name || el.id || selector) + ' with: ' + value;
                }}
                
                function quickSubmit(formSelector) {{
                    const form = document.querySelector(formSelector);
                    if (!form) throw new Error('Form not found: ' + formSelector);
                    
                    form.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    
                    // Try clicking submit button first
                    const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
                    if (submitBtn && submitBtn.offsetParent !== null) {{
                        submitBtn.click();
                        return 'Submitted form by clicking submit button';
                    }} else {{
                        form.submit();
                        return 'Submitted form directly';
                    }}
                }}
                
                function findElements(selector) {{
                    const elements = document.querySelectorAll(selector);
                    return Array.from(elements).map((el, i) => ({{
                        index: i,
                        tag: el.tagName,
                        id: el.id,
                        className: el.className,
                        text: el.textContent.trim().substring(0, 100),
                        visible: el.offsetParent !== null
                    }}));
                }}
                
                function scrollToElement(selector) {{
                    const el = document.querySelector(selector);
                    if (!el) throw new Error('Element not found: ' + selector);
                    el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    return 'Scrolled to element: ' + selector;
                }}
                
                function getCurrentInfo() {{
                    return {{
                        url: window.location.href,
                        title: document.title,
                        readyState: document.readyState,
                        activeElement: document.activeElement ? {{
                            tag: document.activeElement.tagName,
                            id: document.activeElement.id,
                            className: document.activeElement.className
                        }} : null,
                        hasPopups: !!(document.querySelector('.modal, .popup, .overlay, [role="dialog"]')),
                        alerts: Array.from(document.querySelectorAll('.alert, .error, .warning, [role="alert"]')).map(el => el.textContent.trim())
                    }};
                }}
                
                function dismissPopups() {{
                    const selectors = [
                        '.modal .close, .popup .close, .overlay .close',
                        '[role="dialog"] button[aria-label*="close"]',
                        '.cookie-banner button, .cookies-accept, .accept-cookies',
                        '.newsletter-popup .close, .newsletter-modal .close',
                        '.modal-backdrop, .overlay-backdrop',
                        'button[data-dismiss="modal"]'
                    ];
                    
                    for (let selector of selectors) {{
                        const elements = document.querySelectorAll(selector);
                        for (let el of elements) {{
                            if (el.offsetParent !== null) {{
                                el.click();
                                return 'Dismissed popup/modal';
                            }}
                        }}
                    }}
                    
                    // Try ESC key
                    document.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Escape', keyCode: 27}}));
                    return 'Attempted to dismiss popups with ESC';
                }}
                
                // Execute user code
                const result = (function() {{
                    {js_code}
                }})();
                
                return result || "JavaScript executed successfully";
                
            }} catch (error) {{
                console.error('JavaScript execution error:', error);
                return "Error: " + error.toString();
            }}
            """
            
            # Execute with timeout
            result = self.driver.execute_script(enhanced_js)
            
            if isinstance(result, str) and result.startswith("Error:"):
                logger.error(f"JavaScript execution error: {result}")
                self.failed_actions += 1
                return False, result
            else:
                logger.info(f"JavaScript executed successfully: {str(result)[:100]}")
                self.successful_actions += 1
                
                # Wait for any dynamic content to load
                time.sleep(1.5)
                
                return True, str(result)
                
        except Exception as e:
            error_msg = f"Error executing JavaScript: {str(e)}"
            logger.error(error_msg)
            self.failed_actions += 1
            return False, error_msg
    
    def wait_for_condition(self, condition: str = "page_load", duration: int = 3) -> tuple[bool, str]:
        """Enhanced wait with different conditions."""
        try:
            logger.info(f"Waiting for {condition} ({duration} seconds)...")
            
            if condition == "page_load":
                # Wait for page to be ready
                self.wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
                time.sleep(duration)
                return True, f"Page loaded successfully"
                
            elif condition == "element_change":
                # Wait for DOM changes
                initial_length = len(self.driver.find_elements(By.CSS_SELECTOR, "*"))
                time.sleep(duration)
                final_length = len(self.driver.find_elements(By.CSS_SELECTOR, "*"))
                
                if abs(final_length - initial_length) > 5:
                    return True, f"Page content changed (elements: {initial_length} -> {final_length})"
                else:
                    return True, f"Waited {duration} seconds, minimal changes detected"
                    
            else:
                # Default wait
                time.sleep(duration)
                return True, f"Waited for {duration} seconds"
                
        except Exception as e:
            logger.warning(f"Wait condition failed: {e}")
            return True, f"Wait completed with warning: {str(e)}"
    
    def encode_image_base64(self, image_path: str) -> str:
        """Encode image to base64 with error handling."""
        try:
            if not os.path.exists(image_path):
                logger.error(f"Image file not found: {image_path}")
                return ""
                
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
                encoded = base64.b64encode(image_data).decode('utf-8')
                
            logger.debug(f"Image encoded successfully: {len(encoded)} characters")
            return encoded
            
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            return ""
    
    def call_gemini_api_robust(self, messages: List[dict], max_retries: int = 3) -> str:
        """Robust Gemini API call with enhanced retry logic."""
        for attempt in range(max_retries):
            try:
                # Prepare content efficiently
                content = []
                
                # Use recent messages to avoid token limits
                recent_messages = messages[-2:] if len(messages) > 2 else messages
                
                for msg in recent_messages:
                    if msg['role'] == 'user':
                        parts = [{'text': msg['content']}]
                        
                        if msg.get('image') and msg['image']:
                            parts.append({
                                'inline_data': {
                                    'mime_type': 'image/png',
                                    'data': msg['image']
                                }
                            })
                        
                        content.append({'parts': parts})
                
                # Generate content with retry
                response = self.model.generate_content(
                    content,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=1500
                    )
                )
                
                if response and response.text:
                    return response.text.strip()
                else:
                    logger.warning(f"Empty response on attempt {attempt + 1}")
                    
            except Exception as e:
                error_str = str(e).lower()
                
                if "quota" in error_str or "limit" in error_str:
                    logger.error(f"API quota/limit exceeded: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(5 * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        raise
                        
                elif "503" in error_str or "unavailable" in error_str or "429" in error_str:
                    logger.warning(f"API temporarily unavailable (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(3 * (attempt + 1))
                        continue
                    else:
                        raise
                        
                else:
                    logger.error(f"API error (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        raise
        
        return ""
    
    def should_continue_testing(self, current_state_hash: str, iteration: int, max_iterations: int) -> tuple[bool, str]:
        """Enhanced logic to determine if testing should continue."""
        # Check iteration limit
        if iteration >= max_iterations:
            return False, f"Maximum iterations ({max_iterations}) reached"
        
        # Check if page state has changed
        if current_state_hash == self.last_page_hash:
            self.consecutive_same_state_count += 1
        else:
            self.consecutive_same_state_count = 0
            self.last_page_hash = current_state_hash
        
        # Stop if page hasn't changed for too long
        if self.consecutive_same_state_count >= self.max_same_state_count:
            return False, f"Page state unchanged for {self.consecutive_same_state_count} iterations"
        
        # Check for success/failure ratio
        total_actions = self.successful_actions + self.failed_actions
        if total_actions > 0:
            failure_rate = self.failed_actions / total_actions
            if failure_rate > 0.7 and total_actions >= 3:
                return False, f"High failure rate: {failure_rate:.1%} ({self.failed_actions}/{total_actions})"
        
        # Check elapsed time
        elapsed_time = time.time() - self.start_time
        if elapsed_time > 300:  # 5 minutes max
            return False, f"Maximum time limit (5 minutes) reached"
        
        return True, "Continue testing"
    
    def parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """Enhanced AI response parsing with multiple fallback methods."""
        if not response_text:
            return {"action": "end", "error": "Empty response"}
        
        # Try to extract JSON from response
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{[^{}]*"action"[^{}]*\})',
            r'(\{.*?"action".*?\})'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, response_text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    data = json.loads(match.strip())
                    if 'action' in data:
                        return data
                except json.JSONDecodeError:
                    continue
        
        # If no JSON found, try to parse text response
        response_lower = response_text.lower()
        
        # Check for end conditions
        end_keywords = ['complete', 'finished', 'done', 'success', 'found the', 'task accomplished', 'objective achieved']
        if any(keyword in response_lower for keyword in end_keywords):
            return {
                "action": "end",
                "analysis_report": response_text
            }
        
        # Check for JavaScript patterns
        if 'click' in response_lower or 'fill' in response_lower or 'submit' in response_lower:
            # Try to extract JavaScript-like commands
            js_commands = []
            
            # Look for function calls
            if 'click(' in response_lower:
                js_commands.append("quickClick('.btn, button, a, input[type=\"submit\"]')")
            if 'fill(' in response_lower or 'type' in response_lower:
                js_commands.append("return findElements('input, textarea, select')")
            
            if js_commands:
                return {
                    "action": "javascript",
                    "javascript": "; ".join(js_commands)
                }
        
        # Check for wait patterns
        if 'wait' in response_lower or 'loading' in response_lower:
            return {
                "action": "wait",
                "duration": 3
            }
        
        # Default fallback
        return {
            "action": "end",
            "analysis_report": f"Could not parse response. Raw response: {response_text[:500]}..."
        }
    
    def run_enhanced_test(self, initial_url: str, task_description: str, max_iterations: int = 12) -> str:
        """Run the automated web test with enhanced error handling and efficiency."""
        try:
            self.start_time = time.time()
            logger.info(f"Starting enhanced test: {task_description}")
            logger.info(f"Target URL: {initial_url}")
            
            # Navigate to initial URL with retry
            for attempt in range(3):
                try:
                    logger.info(f"Navigating to {initial_url} (attempt {attempt + 1})")
                    self.driver.get(initial_url)
                    
                    # Wait for initial page load
                    self.wait_for_condition("page_load", 3)
                    break
                    
                except Exception as e:
                    logger.warning(f"Navigation attempt {attempt + 1} failed: {e}")
                    if attempt == 2:
                        return f"Failed to navigate to {initial_url} after 3 attempts: {str(e)}"
                    time.sleep(2)
            
            # Take initial screenshot
            screenshot_path = self.take_screenshot_optimized()
            if not screenshot_path:
                logger.warning("Failed to take initial screenshot, continuing without it")
            
            # Get initial page information
            page_info = self.get_enhanced_page_info()
            logger.info(f"Initial page loaded: {page_info['title']} ({len(page_info['interactive_elements'])} interactive elements)")
            
            # Initialize conversation
            initial_content = f"""{SYSTEM_PROMPT}

TASK: {task_description}

CURRENT PAGE ANALYSIS:
- URL: {page_info['url']}
- Title: {page_info['title']}
- Status: {page_info.get('page_status', 'unknown')}
- Interactive elements found: {len(page_info['interactive_elements'])}

KEY INTERACTIVE ELEMENTS:
{json.dumps(page_info['interactive_elements'][:12], indent=1)}

Please analyze the page and provide the next action to complete the task efficiently. 
Focus on the main objective and end the test when the goal is achieved."""
            
            messages = [{
                'role': 'user',
                'content': initial_content,
                'image': self.encode_image_base64(screenshot_path) if screenshot_path else ""
            }]
            
            # Enhanced testing loop
            iteration = 0
            goal_achieved = False
            test_results = []
            
            while iteration < max_iterations and not goal_achieved:
                iteration += 1
                logger.info(f"=== Iteration {iteration}/{max_iterations} ===")
                
                # Check if we should continue testing
                current_state_hash = self.get_page_state_hash()
                should_continue, continue_reason = self.should_continue_testing(current_state_hash, iteration, max_iterations)
                
                if not should_continue:
                    logger.info(f"Stopping test: {continue_reason}")
                    break
                
                try:
                    # Get AI response with enhanced error handling
                    logger.info("Getting AI response...")
                    response_text = self.call_gemini_api_robust(messages)
                    
                    if not response_text:
                        logger.error("Empty response from AI")
                        test_results.append(f"Iteration {iteration}: Empty AI response")
                        continue
                    
                    # Parse AI response
                    response_data = self.parse_ai_response(response_text)
                    action = response_data.get('action', 'unknown')
                    
                    logger.info(f"AI Action: {action}")
                    test_results.append(f"Iteration {iteration}: Action = {action}")
                    
                    # Handle different actions
                    if action == 'end':
                        logger.info("Test completed by AI decision")
                        goal_achieved = True
                        
                        analysis_report = response_data.get('analysis_report', response_text)
                        
                        # Get final page info for complete report
                        final_page_info = self.get_enhanced_page_info()
                        
                        final_report = f"""
=== ENHANCED WEB TESTING AUTOMATION REPORT ===

TASK: {task_description}
STATUS: COMPLETED BY AI
TOTAL ITERATIONS: {iteration}
EXECUTION TIME: {time.time() - self.start_time:.1f} seconds
SUCCESS RATE: {self.successful_actions}/{self.successful_actions + self.failed_actions} actions successful

FINAL PAGE STATE:
- URL: {final_page_info['url']}
- Title: {final_page_info['title']}
- Interactive Elements: {len(final_page_info['interactive_elements'])}

AI ANALYSIS:
{analysis_report}

ITERATION SUMMARY:
{chr(10).join(test_results)}

SCREENSHOTS SAVED: {self.screenshot_count} files in {self.screenshots_dir}
=== END OF REPORT ==="""
                        
                        return final_report
                    
                    elif action == 'javascript':
                        js_code = response_data.get('javascript', '')
                        if not js_code:
                            logger.warning("No JavaScript code provided")
                            messages.append({
                                'role': 'user',
                                'content': "No JavaScript code provided. Please provide specific code or end the test if goal is achieved."
                            })
                            continue
                        
                        logger.info(f"Executing JavaScript: {js_code[:100]}...")
                        success, result = self.execute_javascript_enhanced(js_code)
                        
                        # Take screenshot after action
                        screenshot_path = self.take_screenshot_optimized()
                        
                        if success:
                            # Get updated page info
                            page_info = self.get_enhanced_page_info()
                            
                            feedback_content = f"""JavaScript executed successfully!

RESULT: {result}

UPDATED PAGE STATE:
- URL: {page_info['url']}
- Title: {page_info['title']}
- Interactive Elements: {len(page_info['interactive_elements'])}
- Alerts/Messages: {page_info.get('alerts', [])}

Current page has {len(page_info['interactive_elements'])} interactive elements.

Please continue with the next action or end if the task is complete."""
                            
                            test_results.append(f"Iteration {iteration}: JavaScript SUCCESS - {result[:50]}")
                            
                        else:
                            feedback_content = f"""JavaScript execution failed: {result}

Please try a different approach:
1. Use different selectors or methods
2. Try simpler actions
3. Wait for page to load if needed
4. End the test if the main goal has been achieved despite this error

Current page: {self.driver.current_url}"""
                            
                            test_results.append(f"Iteration {iteration}: JavaScript FAILED - {result[:50]}")
                        
                        messages.append({
                            'role': 'user',
                            'content': feedback_content,
                            'image': self.encode_image_base64(screenshot_path) if screenshot_path else ""
                        })
                    
                    elif action == 'wait':
                        duration = response_data.get('duration', 3)
                        duration = max(1, min(duration, 10))  # Clamp between 1-10 seconds
                        
                        condition = response_data.get('condition', 'page_load')
                        logger.info(f"Waiting for {condition} ({duration}s)...")
                        
                        success, result = self.wait_for_condition(condition, duration)
                        
                        # Take screenshot after wait
                        screenshot_path = self.take_screenshot_optimized()
                        
                        # Get updated page state
                        page_info = self.get_enhanced_page_info()
                        
                        feedback_content = f"""Wait completed: {result}

CURRENT PAGE STATE:
- URL: {page_info['url']}
- Title: {page_info['title']}
- Ready State: {page_info.get('ready_state', 'unknown')}
- Interactive Elements: {len(page_info['interactive_elements'])}

Please provide the next action or end if task is complete."""
                        
                        messages.append({
                            'role': 'user',
                            'content': feedback_content,
                            'image': self.encode_image_base64(screenshot_path) if screenshot_path else ""
                        })
                        
                        test_results.append(f"Iteration {iteration}: WAIT - {result}")
                    
                    else:
                        logger.warning(f"Unknown action: {action}")
                        messages.append({
                            'role': 'user',
                            'content': f"Unknown action '{action}'. Please use 'javascript', 'wait', or 'end'. Raw response: {response_text[:200]}"
                        })
                        test_results.append(f"Iteration {iteration}: UNKNOWN ACTION - {action}")
                
                except Exception as e:
                    logger.error(f"Error in iteration {iteration}: {e}")
                    
                    # Take screenshot for debugging
                    screenshot_path = self.take_screenshot_optimized()
                    
                    error_feedback = f"""Error occurred in iteration {iteration}: {str(e)}

Current page: {getattr(self.driver, 'current_url', 'unknown')}

Please try a different approach or end the test if the main objective has been achieved."""
                    
                    messages.append({
                        'role': 'user',
                        'content': error_feedback,
                        'image': self.encode_image_base64(screenshot_path) if screenshot_path else ""
                    })
                    
                    test_results.append(f"Iteration {iteration}: ERROR - {str(e)[:50]}")
                    
                    # Don't break on single errors, continue testing
                    continue
            
            # Generate final report if loop ended without explicit completion
            if not goal_achieved:
                logger.info("Test completed - generating final report...")
                
                # Get final page state
                final_page_info = self.get_enhanced_page_info()
                final_screenshot = self.take_screenshot_optimized()
                
                # Try to get final analysis from AI
                final_analysis = "Test completed due to iteration/time limits."
                try:
                    final_response = self.call_gemini_api_robust([{
                        'role': 'user',
                        'content': f"""Please provide a final analysis of the test results for task: "{task_description}"

Current page: {final_page_info['url']}
Title: {final_page_info['title']}
Interactive elements: {len(final_page_info['interactive_elements'])}

Was the task completed successfully? What was achieved?""",
                        'image': self.encode_image_base64(final_screenshot) if final_screenshot else ""
                    }], max_retries=1)
                    
                    if final_response:
                        final_analysis = final_response
                        
                except Exception as e:
                    logger.warning(f"Could not get final analysis: {e}")
                
                # Generate comprehensive final report
                final_report = f"""
=== ENHANCED WEB TESTING AUTOMATION REPORT ===

TASK: {task_description}
STATUS: COMPLETED ({continue_reason if 'continue_reason' in locals() else 'Loop ended'})
TOTAL ITERATIONS: {iteration}
EXECUTION TIME: {time.time() - self.start_time:.1f} seconds
SUCCESS RATE: {self.successful_actions}/{self.successful_actions + self.failed_actions if self.successful_actions + self.failed_actions > 0 else 1} actions successful

INITIAL PAGE: {initial_url}
FINAL PAGE: {final_page_info['url']}
FINAL TITLE: {final_page_info['title']}

FINAL ANALYSIS:
{final_analysis}

DETAILED ITERATION LOG:
{chr(10).join(test_results)}

TECHNICAL DETAILS:
- Screenshots captured: {self.screenshot_count}
- Successful actions: {self.successful_actions}
- Failed actions: {self.failed_actions}
- Page state changes detected: {iteration - self.consecutive_same_state_count}

SCREENSHOTS DIRECTORY: {self.screenshots_dir}
=== END OF REPORT ==="""
                
                return final_report
            
        except Exception as e:
            logger.error(f"Critical error during test execution: {e}")
            
            # Generate error report
            error_report = f"""
=== ENHANCED WEB TESTING AUTOMATION - ERROR REPORT ===

TASK: {task_description}
STATUS: FAILED
ERROR: {str(e)}
EXECUTION TIME: {time.time() - self.start_time:.1f} seconds

CURRENT STATE:
- URL: {getattr(self.driver, 'current_url', 'unknown') if self.driver else 'Driver not initialized'}
- Iterations completed: {iteration if 'iteration' in locals() else 0}
- Screenshots taken: {self.screenshot_count}

ERROR DETAILS:
{str(e)}

PARTIAL RESULTS:
{chr(10).join(test_results) if 'test_results' in locals() else 'No results recorded'}

=== END OF ERROR REPORT ==="""
            
            return error_report
            
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Enhanced cleanup with better error handling."""
        logger.info("Starting cleanup...")
        
        try:
            if self.driver:
                # Try to close all windows
                try:
                    for handle in self.driver.window_handles:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                except:
                    pass
                
                # Quit the driver
                try:
                    self.driver.quit()
                    logger.info("WebDriver closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing WebDriver: {e}")
                    
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        # Reset instance variables
        self.driver = None
        self.wait = None
        
        logger.info("Cleanup completed")

def main():
    """Enhanced main function with better error handling and user feedback."""
    try:
        # Get API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("ERROR: Please set GEMINI_API_KEY environment variable")
            print("You can get an API key from: https://ai.google.dev/")
            return
        
        print("🚀 Starting Enhanced Web Testing Automation...")
        print("=" * 60)
        
        # Initialize automation
        automation = EnhancedWebTestingAutomation(
            gemini_api_key=api_key,
            chrome_driver_path=None  # Let it auto-detect
        )
        
        # Setup browser
        print("🔧 Setting up browser...")
        if not automation.setup_selenium(headless=False):
            print("❌ Failed to setup browser. Please ensure Chrome is installed.")
            return
        
        print("✅ Browser setup complete!")
        
        # Configuration
        initial_url = "https://www.edx.org/"
        task_description = "Search for 'Python' courses, find and analyze course details, check enrollment process and pricing information."
        max_iterations = 12
        
        print(f"🎯 Task: {task_description}")
        print(f"🌐 Target URL: {initial_url}")
        print(f"⚙️ Max iterations: {max_iterations}")
        print("\n🤖 Starting automated test execution...\n")
        
        # Run the enhanced test
        start_time = time.time()
        report = automation.run_enhanced_test(initial_url, task_description, max_iterations)
        execution_time = time.time() - start_time
        
        # Display results
        print("\n" + "=" * 80)
        print("🎉 TEST EXECUTION COMPLETED!")
        print("=" * 80)
        print(report)
        print("=" * 80)
        print(f"⏱️ Total execution time: {execution_time:.1f} seconds")
        print("=" * 80)
        
        # Save detailed report
        report_path = automation.screenshots_dir / f"enhanced_report_{int(time.time())}.txt"
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)
                f.write(f"\n\nExecution completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                f.write(f"\nTotal execution time: {execution_time:.1f} seconds")
            
            print(f"📄 Detailed report saved: {report_path}")
            
        except Exception as e:
            print(f"⚠️ Could not save report file: {e}")
        
        print(f"📸 Screenshots saved in: {automation.screenshots_dir}")
        print("\n✅ Enhanced Web Testing Automation completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
        
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        logger.error(f"Critical error in main: {e}")
        
    finally:
        print("\n🔄 Cleaning up resources...")

if __name__ == "__main__":
    main()