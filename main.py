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
from selenium.common.exceptions import TimeoutException, WebDriverException
import google.generativeai as genai
from pathlib import Path
import logging
from dotenv import load_dotenv
import base64
import hashlib

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Enhanced system prompt for faster processing
SYSTEM_PROMPT = """You are an expert web testing automation assistant. Your task is to help automate web testing efficiently by analyzing screenshots and page structure, then providing focused JavaScript actions.

Available actions:
1. "javascript" - Execute JavaScript code to interact with the page
2. "wait" - Wait for page elements to load or change
3. "end" - End the test and provide analysis report

Guidelines for EFFICIENT testing:
- Use specific, reliable selectors (prefer id, class, or tag names)
- Focus on the main task - avoid unnecessary exploration
- Use document.querySelector() or document.querySelectorAll()
- Handle errors gracefully but move forward quickly
- Provide concise analysis when ending the test
- If you achieve the main goal, end the test immediately

Response format should be JSON with required "action" field and optional "javascript" or "analysis_report" fields.

IMPORTANT: Be decisive and efficient. If you find what you're looking for or complete the task, immediately use the "end" action."""

class OptimizedWebTestingAutomation:
    def __init__(self, gemini_api_key: str, chrome_driver_path: Optional[str] = None):
        """
        Initialize the Web Testing Automation system.
        
        Args:
            gemini_api_key: API key for Gemini
            chrome_driver_path: Path to Chrome driver (optional)
        """
        # Configure Gemini
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        self.driver = None
        self.conversation_history = []
        self.screenshot_count = 0
        self.screenshots_dir = Path("test_screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)
        self.chrome_driver_path = chrome_driver_path
        
        # Optimization flags
        self.page_state_cache = {}
        self.last_page_hash = None
        self.consecutive_same_state_count = 0
        self.max_same_state_count = 3
        
    def setup_selenium(self, headless: bool = False) -> None:
        """
        Set up Selenium WebDriver with optimized Chrome options.
        """
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        
        # Optimized Chrome options for better performance
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-images")  # Speed up loading
        chrome_options.add_argument("--disable-javascript-harmony-shipping")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-client-side-phishing-detection")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--hide-scrollbars")
        chrome_options.add_argument("--metrics-recording-only")
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--safebrowsing-disable-auto-update")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Performance-focused preferences
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2,  # Block images for speed
            "profile.default_content_setting_values.plugins": 1,
            "profile.content_settings.plugin_whitelist.adobe-flash-player": 1,
            "profile.content_settings.exceptions.plugins.*,*.per_resource.adobe-flash-player": 1
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            if self.chrome_driver_path:
                service = Service(self.chrome_driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
                
            # Optimized timeouts
            self.driver.implicitly_wait(5)  # Reduced from 10
            self.driver.set_page_load_timeout(20)  # Reduced from 30
            
            # Set smaller window size for faster rendering
            self.driver.set_window_size(1280, 720)
            
            logger.info("Selenium WebDriver initialized successfully with optimizations")
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise
        
    def take_screenshot(self) -> str:
        """
        Take a screenshot and save it to the screenshots directory.
        """
        try:
            screenshot_path = self.screenshots_dir / f"screenshot_{self.screenshot_count:04d}.png"
            self.driver.save_screenshot(str(screenshot_path))
            self.screenshot_count += 1
            logger.info(f"Screenshot saved: {screenshot_path}")
            return str(screenshot_path)
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return ""
    
    def get_page_state_hash(self) -> str:
        """
        Generate a hash of the current page state to detect changes.
        """
        try:
            # Get essential page elements for hashing
            url = self.driver.current_url
            title = self.driver.title
            
            # Get key interactive elements
            forms_count = len(self.driver.find_elements(By.TAG_NAME, "form"))
            inputs_count = len(self.driver.find_elements(By.TAG_NAME, "input"))
            buttons_count = len(self.driver.find_elements(By.TAG_NAME, "button"))
            
            state_string = f"{url}|{title}|{forms_count}|{inputs_count}|{buttons_count}"
            return hashlib.md5(state_string.encode()).hexdigest()
        except:
            return ""
    
    def get_focused_page_info(self) -> Dict[str, Any]:
        """
        Get only the most essential page information for faster processing.
        """
        try:
            page_info = {
                "url": self.driver.current_url,
                "title": self.driver.title,
                "interactive_elements": []
            }
            
            # Get only interactive elements (forms, inputs, buttons, links)
            elements_selectors = [
                ("form", "form"),
                ("input", "input"),
                ("button", "button"),
                ("select", "select"),
                ("textarea", "textarea"),
                ("a", "a[href]")
            ]
            
            for element_type, selector in elements_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)[:5]  # Limit to 5 each
                for i, elem in enumerate(elements):
                    try:
                        elem_info = {
                            "type": element_type,
                            "index": i,
                            "id": elem.get_attribute("id") or "",
                            "class": elem.get_attribute("class") or "",
                            "text": (elem.text or elem.get_attribute("value") or "")[:50]  # Truncate text
                        }
                        
                        # Add type-specific attributes
                        if element_type == "input":
                            elem_info["input_type"] = elem.get_attribute("type") or "text"
                            elem_info["name"] = elem.get_attribute("name") or ""
                        elif element_type == "a":
                            elem_info["href"] = elem.get_attribute("href") or ""
                        elif element_type == "form":
                            elem_info["action"] = elem.get_attribute("action") or ""
                            elem_info["method"] = elem.get_attribute("method") or "GET"
                        
                        page_info["interactive_elements"].append(elem_info)
                    except:
                        continue
            
            return page_info
            
        except Exception as e:
            logger.error(f"Failed to get page info: {e}")
            return {"url": "", "title": "", "interactive_elements": []}
    
    def execute_javascript_optimized(self, js_code: str) -> tuple[bool, str]:
        """
        Execute JavaScript code with optimized error handling and faster execution.
        """
        try:
            # Streamlined JavaScript wrapper
            wrapped_js = f"""
            try {{
                function quickClick(selector) {{
                    const el = document.querySelector(selector);
                    if (!el) throw new Error('Element not found: ' + selector);
                    el.scrollIntoView({{block: 'center'}});
                    el.click();
                    return 'Clicked: ' + selector;
                }}
                
                function quickFill(selector, value) {{
                    const el = document.querySelector(selector);
                    if (!el) throw new Error('Input not found: ' + selector);
                    el.scrollIntoView({{block: 'center'}});
                    el.focus();
                    el.value = value;
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'Filled: ' + selector;
                }}
                
                const result = (function() {{
                    {js_code}
                }})();
                
                return result || "Success";
                
            }} catch (error) {{
                return "Error: " + error.toString();
            }}
            """
            
            result = self.driver.execute_script(wrapped_js)
            
            if isinstance(result, str) and result.startswith("Error:"):
                logger.error(f"JavaScript execution error: {result}")
                return False, result
            else:
                logger.info("JavaScript executed successfully")
                time.sleep(1)  # Reduced wait time
                return True, str(result)
                
        except Exception as e:
            error_msg = f"Error executing JavaScript: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def wait_action_optimized(self, duration: int = 2) -> tuple[bool, str]:
        """
        Optimized wait with shorter default duration.
        """
        try:
            logger.info(f"Waiting for {duration} seconds...")
            time.sleep(duration)
            return True, f"Waited for {duration} seconds"
        except Exception as e:
            return False, f"Error during wait: {str(e)}"
    
    def encode_image_optimized(self, image_path: str) -> str:
        """
        Encode image to base64 with compression for faster API calls.
        """
        try:
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
                # For very large images, we could add compression here
                return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            return ""
    
    def call_gemini_api_optimized(self, messages: List[dict]) -> str:
        """
        Optimized Gemini API call with better retry logic and faster processing.
        """
        max_retries = 2  # Reduced retries
        retry_delay = 3  # Shorter delay
        
        for retry_count in range(max_retries):
            try:
                # Prepare content more efficiently
                content = []
                
                # Only use the last few messages to reduce token usage
                recent_messages = messages[-3:] if len(messages) > 3 else messages
                
                for msg in recent_messages:
                    if msg['role'] == 'user':
                        if 'image' in msg and msg['image']:
                            content.append({
                                'parts': [
                                    {'text': msg['content']},
                                    {
                                        'inline_data': {
                                            'mime_type': 'image/png',
                                            'data': msg['image']
                                        }
                                    }
                                ]
                            })
                        else:
                            content.append({'parts': [{'text': msg['content']}]})
                
                # Make the API call
                response = self.model.generate_content(content)
                return response.text
                
            except Exception as e:
                if "503" in str(e) or "429" in str(e) or "unavailable" in str(e).lower():
                    if retry_count < max_retries - 1:
                        logger.warning(f"API unavailable, retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(f"API unavailable after {max_retries} attempts")
                        raise
                else:
                    logger.error(f"API error: {e}")
                    raise
        
        return ""
    
    def should_continue_testing(self, current_state_hash: str) -> bool:
        """
        Determine if testing should continue based on page state changes.
        """
        if current_state_hash == self.last_page_hash:
            self.consecutive_same_state_count += 1
        else:
            self.consecutive_same_state_count = 0
            self.last_page_hash = current_state_hash
        
        # Stop if page hasn't changed for too long
        return self.consecutive_same_state_count < self.max_same_state_count
    
    def run_test_optimized(self, initial_url: str, task_description: str) -> str:
        """
        Run the automated web test with optimizations for faster execution.
        """
        try:
            # Navigate to initial URL
            logger.info(f"Navigating to {initial_url}")
            self.driver.get(initial_url)
            time.sleep(3)  # Reduced initial wait
            
            # Take initial screenshot
            screenshot_path = self.take_screenshot()
            if not screenshot_path:
                return "Failed to take initial screenshot"
            
            # Get focused page information
            page_info = self.get_focused_page_info()
            
            # Initialize conversation with enhanced prompt
            messages = [
                {
                    'role': 'user',
                    'content': f"{SYSTEM_PROMPT}\n\nTask: {task_description}\n\nCurrent page: {page_info['url']}\nTitle: {page_info['title']}\n\nInteractive elements found: {len(page_info['interactive_elements'])}\n\nKey elements:\n{json.dumps(page_info['interactive_elements'][:10], indent=1)}\n\nPlease analyze and provide the next action to complete the task efficiently.",
                    'image': self.encode_image_optimized(screenshot_path)
                }
            ]
            
            # Optimized testing loop
            iteration = 0
            max_iterations = 10  # Significantly reduced
            goal_achieved = False
            
            while iteration < max_iterations and not goal_achieved:
                iteration += 1
                logger.info(f"Iteration {iteration}/{max_iterations}")
                
                # Check if we should continue based on page state
                current_state_hash = self.get_page_state_hash()
                if not self.should_continue_testing(current_state_hash):
                    logger.info("Page state hasn't changed, likely task is complete or stuck")
                    break
                
                try:
                    # Get response from Gemini
                    response_text = self.call_gemini_api_optimized(messages)
                    
                    if not response_text:
                        logger.error("Empty response from Gemini")
                        break
                    
                    # Parse JSON response with better error handling
                    try:
                        response_text = response_text.strip()
                        if response_text.startswith('```json'):
                            response_text = response_text[7:]
                        if response_text.endswith('```'):
                            response_text = response_text[:-3]
                        
                        response_data = json.loads(response_text)
                        logger.info(f"Action: {response_data.get('action', 'unknown')}")
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse JSON response: {response_text[:200]}...")
                        # Try to detect if task is complete from text
                        if any(keyword in response_text.lower() for keyword in ['complete', 'found', 'success', 'finished']):
                            return f"Task completed successfully.\n\nFinal Analysis:\n{response_text}"
                        continue
                    
                    # Handle actions
                    if response_data.get('action') == 'end':
                        logger.info("Test completed by AI")
                        goal_achieved = True
                        return response_data.get('analysis_report', response_text)
                    
                    elif response_data.get('action') == 'javascript':
                        js_code = response_data.get('javascript', '')
                        if js_code:
                            success, result = self.execute_javascript_optimized(js_code)
                            
                            # Take screenshot after action
                            screenshot_path = self.take_screenshot()
                            
                            # Get updated page info (only if action was successful)
                            if success:
                                page_info = self.get_focused_page_info()
                                content = f"JavaScript executed successfully. Result: {result}\n\nUpdated page: {page_info['url']}\nInteractive elements: {len(page_info['interactive_elements'])}"
                            else:
                                content = f"JavaScript failed: {result}\n\nPlease try a different approach or end the test if the goal is achieved."
                            
                            messages.append({
                                'role': 'user',
                                'content': content,
                                'image': self.encode_image_optimized(screenshot_path) if screenshot_path else ""
                            })
                        else:
                            messages.append({
                                'role': 'user',
                                'content': "No JavaScript code provided. Please provide code or end the test."
                            })
                    
                    elif response_data.get('action') == 'wait':
                        success, result = self.wait_action_optimized(2)  # Shorter wait
                        screenshot_path = self.take_screenshot()
                        
                        messages.append({
                            'role': 'user',
                            'content': f"Wait completed: {result}",
                            'image': self.encode_image_optimized(screenshot_path) if screenshot_path else ""
                        })
                    
                    else:
                        logger.error(f"Unknown action: {response_data.get('action')}")
                        messages.append({
                            'role': 'user',
                            'content': f"Unknown action: {response_data.get('action')}. Use 'javascript', 'wait', or 'end'."
                        })
                    
                except Exception as e:
                    logger.error(f"Error in iteration {iteration}: {e}")
                    messages.append({
                        'role': 'user',
                        'content': f"Error occurred: {str(e)}. Please try a different approach or end the test."
                    })
            
            # Generate final report if loop ended without explicit completion
            if not goal_achieved:
                final_message = f"Test completed after {iteration} iterations.\n\nFinal page: {self.driver.current_url}\n\nTask: {task_description}\n\nStatus: Maximum iterations reached or page state stabilized."
                
                # Try to get a final analysis from Gemini
                try:
                    final_screenshot = self.take_screenshot()
                    final_analysis = self.call_gemini_api_optimized([{
                        'role': 'user',
                        'content': f"Please provide a brief analysis of the current state and whether the task '{task_description}' was completed successfully.",
                        'image': self.encode_image_optimized(final_screenshot) if final_screenshot else ""
                    }])
                    
                    if final_analysis:
                        final_message += f"\n\nFinal Analysis:\n{final_analysis}"
                        
                except Exception as e:
                    logger.error(f"Failed to get final analysis: {e}")
                
                return final_message
            
        except Exception as e:
            logger.error(f"Error during test execution: {e}")
            return f"Test failed with error: {str(e)}"
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser closed")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")

def main():
    """Example usage of the Optimized Web Testing Automation system."""
    # Get API key from environment variable
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Please set GEMINI_API_KEY environment variable")
    
    # Create automation instance
    automation = OptimizedWebTestingAutomation(
        gemini_api_key=api_key,
        chrome_driver_path=None
    )
    
    try:
        # Set up Selenium with optimizations
        automation.setup_selenium(headless=False)
        
        # Run optimized test
        initial_url = "https://www.naukri.com/"
        task_description = "Search for 'Python Developer' jobs in 'Bangalore'. Apply location and experience filters if available."
        
        report = automation.run_test_optimized(initial_url, task_description)
        
        print("\n" + "="*50)
        print("FINAL REPORT")
        print("="*50)
        print(report)
        print("="*50 + "\n")
        
        # Save report to file
        report_path = automation.screenshots_dir / "final_report.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        logger.info(f"Report saved to: {report_path}")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise

if __name__ == "__main__":
    main()