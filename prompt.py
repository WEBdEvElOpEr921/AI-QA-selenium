# Test different websites with your automation system

SYSTEM_PROMPT = '''You are an expert QA for a large enterprise firm. You will receive website screenshots and HTML content. Your task is to navigate the website and check for any bugs/issues. The user can specify some task that you will have to accomplish and make sure everything works fine.

IMPORTANT RULES FOR FORM INPUTS AND INTERACTIONS:

1. For setting input values (CRITICAL - use this method for all text/password/email inputs):
   ```javascript
   const setValue = (id, val) => { 
     const el = document.getElementById(id); 
     const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; 
     setter.call(el, val); 
     el.dispatchEvent(new Event('input', {bubbles: true})); 
   }; 
   setValue('email', 'example@email.com');
   ```
   NEVER use direct element.value = 'something' as it won't work with modern frameworks.

2. For clicking elements:
   ```javascript
   document.querySelector('button[type="submit"]').click();
   ```
   Add small delays if needed: setTimeout(() => element.click(), 100);

3. For selecting elements:
   - Use element IDs when available: document.getElementById('id')
   - Use simple class names: document.querySelector('.classname')
   - Use element attributes: document.querySelector('[data-attribute="value"]')
   - Avoid complex CSS selectors with pseudo-classes like :hover, :focus

4. When filling forms:
   - Fill one field at a time
   - Use the setValue method above for each input
   - Wait briefly between actions if needed
   - Click submit only after all fields are filled

5. For navigation:
   ```javascript
   window.location.href = 'https://example.com';
   ```

You can provide javascript for various actions (clicking buttons, entering input, visiting URLs). If you encounter an error, try a different selector approach.
You can provide action to wait in case the page is loading or still executing some script. Use wait script to give browser some time to complete current activity.
After you have successfully completed your analysis, submit action as end with a detailed report. For each response, do only ONE action at a time (like filling one input field OR clicking one button). Don't try to accomplish multiple steps in a single response.
You Are allowed to use clicks to go to different inputs/buttons.
Example valid responses:
- Setting email: `const setValue = (id, val) => { const el = document.getElementById(id); const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; setter.call(el, val); el.dispatchEvent(new Event('input', {bubbles: true})); }; setValue('email', 'test@example.com');`
- Clicking button: `document.querySelector('button[type="submit"]').click();`
- Navigating: `window.location.href = 'https://app.example.com/login';`'''

# Example test configurations
TEST_SCENARIOS = {
    "1": {
        "name": "E-commerce Demo",
        "url": "https://demo.opencart.com/",
        "task": "Search for 'iPhone', add a product to cart, and proceed to checkout. Test the complete shopping flow."
    },
    
    "2": {
        "name": "Form Testing",
        "url": "https://demoqa.com/text-box",
        "task": "Fill out all form fields with sample data and submit the form. Verify the output is displayed correctly."
    },
    
    "3": {
        "name": "Login Testing",
        "url": "https://the-internet.herokuapp.com/login",
        "task": "Test login functionality. Try with invalid credentials first, then use valid credentials (username: tomsmith, password: SuperSecretPassword!)"
    },
    
    "4": {
        "name": "Interactive Elements",
        "url": "https://demoqa.com/buttons",
        "task": "Test all button interactions - single click, double click, and right click buttons. Verify all interactions work properly."
    },
    
    "5": {
        "name": "Job Portal Search",
        "url": "https://www.naukri.com/",
        "task": "Search for 'Python Developer' jobs in 'Bangalore'. Apply location and experience filters if available."
    },
    
    "6": {
        "name": "Real Estate Search", 
        "url": "https://www.99acres.com/",
        "task": "Search for residential properties in Mumbai. Try to apply filters for 2BHK apartments."
    },
    
    "7": {
        "name": "Travel Booking",
        "url": "https://www.makemytrip.com/",
        "task": "Search for flights from Delhi to Mumbai for next week. Analyze the search results and filters."
    },
    
    "8": {
        "name": "Online Banking Demo",
        "url": "https://demo.testfire.net/",
        "task": "Navigate through the banking demo site. Try to login and explore different sections."
    },
    
    "9": {
        "name": "Government Services",
        "url": "https://www.digitalindia.gov.in/",
        "task": "Navigate through various government services. Check accessibility and user experience."
    },
    
    "10": {
        "name": "Educational Platform",
        "url": "https://www.edx.org/",
        "task": "Search for 'Python' courses. Browse course details and check enrollment process."
    }
}

def run_website_test(scenario_number):
    """
    Run test for a specific scenario
    """
    import os
    from your_automation_script import WebTestingAutomation  # Import your main class
    
    if scenario_number not in TEST_SCENARIOS:
        print("Invalid scenario number!")
        return
    
    scenario = TEST_SCENARIOS[scenario_number]
    
    print(f"\n🚀 Starting Test: {scenario['name']}")
    print(f"🌐 URL: {scenario['url']}")
    print(f"📋 Task: {scenario['task']}")
    print("-" * 50)
    
    # Get API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Please set GEMINI_API_KEY environment variable")
    
    # Create automation instance
    automation = WebTestingAutomation(
        gemini_api_key=api_key,
        chrome_driver_path=None
    )
    
    try:
        # Set up Selenium
        automation.setup_selenium(headless=False)
        
        # Run test
        report = automation.run_test(scenario['url'], scenario['task'])
        
        print(f"\n✅ Test Completed: {scenario['name']}")
        print("=" * 60)
        print("FINAL REPORT:")
        print("=" * 60)
        print(report)
        print("=" * 60)
        
        # Save report
        report_path = automation.screenshots_dir / f"report_{scenario['name'].replace(' ', '_')}.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"Test: {scenario['name']}\n")
            f.write(f"URL: {scenario['url']}\n") 
            f.write(f"Task: {scenario['task']}\n")
            f.write("=" * 50 + "\n")
            f.write(report)
        
        print(f"\n📁 Report saved to: {report_path}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise

# Interactive menu
def main():
    print("🤖 AI Web Testing Automation")
    print("=" * 40)
    
    for key, scenario in TEST_SCENARIOS.items():
        print(f"{key}. {scenario['name']}")
        print(f"   URL: {scenario['url']}")
        print(f"   Task: {scenario['task'][:60]}...")
        print()
    
    choice = input("Enter scenario number (1-10): ").strip()
    
    if choice in TEST_SCENARIOS:
        run_website_test(choice)
    else:
        print("❌ Invalid choice!")

if __name__ == "__main__":
    main()