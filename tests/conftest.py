# tests/conftest.py
#
# Shared fixtures and helper functions for the Library Management System
# Selenium test suite.
#
# Every test file in tests/ automatically has access to everything defined
# here — no imports needed for fixtures.
#
# ─────────────────────────────────────────────────────────────────────────────
# PREREQUISITES (run once before testing):
#   cd Library-Management-System
#   pip install -r tests/requirements-test.txt
#
# Run all tests:
#   pytest
#
# Run only smoke tests:
#   pytest -m smoke
# ─────────────────────────────────────────────────────────────────────────────

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# Change BASE_URL if Flask is running on a different port.
# Change ADMIN_* / USER_* if your DB credentials differ.
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "http://127.0.0.1:5000"

ADMIN_USERNAME = "admin"       # ← update to match your DB
ADMIN_PASSWORD = "admin"       # ← update to match your DB

USER_USERNAME  = "sajal"    # ← update to match your DB
USER_PASSWORD  = "admin"    # ← update to match your DB


# ─────────────────────────────────────────────────────────────────────────────
# DRIVER FIXTURE
# Scope = "function" means a fresh browser is started for every test.
# This keeps tests isolated — one test's state cannot bleed into another.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def driver():
    """
    Starts a Chrome browser before each test and closes it after.

    webdriver-manager automatically downloads the correct ChromeDriver
    version for your installed Chrome — no manual driver management needed.
    """
    service = Service(ChromeDriverManager().install())

    options = webdriver.ChromeOptions()

    # Enable headless mode if running in CI (GitHub Actions) or if HEADLESS env var is set
    import os
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("HEADLESS") == "true":
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        # Prevent headless Chrome from suppressing alerts when page navigations
        # race with pending window.alert() calls.
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-backgrounding-occluded-windows")

    # Suppress Chrome's "DevTools listening" console noise
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    # Disable the "Chrome is being controlled by automated software" bar
    options.add_experimental_option("useAutomationExtension", False)

    browser = webdriver.Chrome(service=service, options=options)

    # Implicit wait: Selenium will retry finding elements for up to 5 seconds
    # before raising NoSuchElementException. Keeps tests less brittle.
    browser.implicitly_wait(5)

    # Maximise so all nav links and buttons are visible without scrolling
    browser.maximize_window()

    yield browser  # hand the browser to the test

    # Best-effort alert cleanup: if a test crashes while an alert is open,
    # dismiss it so browser.quit() does not hang on Windows.
    try:
        browser.switch_to.alert.dismiss()
    except Exception:
        pass

    browser.quit()  # always close after the test, even if it failed


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: navigate to a URL relative to BASE_URL
# ─────────────────────────────────────────────────────────────────────────────

def go_to(driver, path):
    """
    Navigate the browser to BASE_URL + path.

    Example:
        go_to(driver, "/admin_login")   →   http://127.0.0.1:5000/admin_login
        go_to(driver, "/")              →   http://127.0.0.1:5000/
    """
    driver.get(BASE_URL + path)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: log in as Admin
#
# Flow:  / → select "Admin" → submit → /admin_login → fill form → submit
#        → lands on /admin_dashboard
# ─────────────────────────────────────────────────────────────────────────────

def login_as_admin(driver, username=ADMIN_USERNAME, password=ADMIN_PASSWORD,
                   expect_success=True):
    """
    Performs a complete admin login sequence starting from the landing page.

    Parameters
    ----------
    driver         : active WebDriver instance
    username       : admin username (defaults to ADMIN_USERNAME constant above)
    password       : admin password (defaults to ADMIN_PASSWORD constant above)
    expect_success : if True (default), waits for the /admin_dashboard redirect
                     after form submission — use for valid-credential tests.
                     if False, returns immediately after clicking Submit so the
                     caller can inspect the login page error state — use for
                     invalid-credential tests.

    Returns
    -------
    None
    """
    # Step 1: Go to landing page
    go_to(driver, "/")

    # Step 2: Choose "Admin" from the dropdown
    login_type_select = Select(driver.find_element(By.ID, "loginType"))
    login_type_select.select_by_value("admin")

    # Step 3: Click the Login button to be redirected to /admin_login
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Step 4: Wait until the admin login form is visible
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, "adminUsername")))

    # Step 5: Fill in credentials
    driver.find_element(By.ID, "adminUsername").send_keys(username)
    driver.find_element(By.ID, "adminPassword").send_keys(password)

    # Step 6: Submit the form
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Step 7: Only wait for the dashboard redirect when valid credentials are used.
    # Invalid-credential tests set expect_success=False and assert the error state
    # themselves — skipping this wait prevents a TimeoutException in those tests.
    if expect_success:
        wait.until(EC.url_contains("/admin_dashboard"))


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: log in as User
#
# Flow:  / → select "User" → submit → /user_login → fill form → submit
#        → lands on /user_dashboard
# ─────────────────────────────────────────────────────────────────────────────

def login_as_user(driver, username=USER_USERNAME, password=USER_PASSWORD,
                  expect_success=True):
    """
    Performs a complete user login sequence starting from the landing page.

    Parameters
    ----------
    driver         : active WebDriver instance
    username       : user username (defaults to USER_USERNAME constant above)
    password       : user password (defaults to USER_PASSWORD constant above)
    expect_success : if True (default), waits for the /user_dashboard redirect
                     after form submission — use for valid-credential tests.
                     if False, returns immediately after clicking Submit so the
                     caller can inspect the login page error state — use for
                     invalid-credential tests.

    Returns
    -------
    None
    """
    # Step 1: Go to landing page
    go_to(driver, "/")

    # Step 2: Choose "User" from the dropdown
    login_type_select = Select(driver.find_element(By.ID, "loginType"))
    login_type_select.select_by_value("user")

    # Step 3: Click Login → redirected to /user_login
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Step 4: Wait for the user login form
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, "userUsername")))

    # Step 5: Fill in credentials
    driver.find_element(By.ID, "userUsername").send_keys(username)
    driver.find_element(By.ID, "userPassword").send_keys(password)

    # Step 6: Submit
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Step 7: Only wait for the dashboard redirect when valid credentials are used.
    # Invalid-credential tests set expect_success=False and assert the error state
    # themselves — skipping this wait prevents a TimeoutException in those tests.
    if expect_success:
        wait.until(EC.url_contains("/user_dashboard"))


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: JavaScript alert() interceptor (primary AJAX alert strategy)
#
# How the headless Chrome "suppressed dialog" bug occurs:
#   1. AJAX call completes → script.js calls window.alert()
#   2. Selenium waits for the native dialog via alert_is_present()
#   3. BUT: if Chrome’s modal stack is not fully empty from any prior
#      navigation or dialog, it silently drops the new alert() call and
#      logs: "window.alert() dialog was suppressed because another
#             browser modal dialog was already showing"
#   4. accept_alert() times out waiting for a dialog that was never shown.
#
# The only 100%-reliable fix is to prevent a native dialog from being
# created in the first place. We do this by overriding window.alert()
# with a JavaScript shim BEFORE clicking the button. The shim stores the
# message in a JS variable instead of opening a dialog. No native modal
# → nothing to suppress → Selenium polls the variable instead.
# ─────────────────────────────────────────────────────────────────────────────

def intercept_next_alert(driver):
    """
    Injects a JavaScript shim that overrides window.alert() on the current
    page BEFORE the action that will trigger it.

    Instead of opening a native browser dialog (which headless Chrome can
    silently suppress), the shim records the alert message in sessionStorage.

    WHY sessionStorage instead of window variables:
    -----------------------------------------------
    When a successful issue/return fires window.alert() followed immediately
    by location.reload(), the page reloads BEFORE Python's polling loop
    (get_intercepted_alert) can read window.__alertFired. The reload wipes
    all window-level variables. sessionStorage survives same-origin reloads,
    so the captured message is still readable from the new page's context.

    Keys written:
        __alertFired = '1'             set when alert() is called
        __alertText  = '<message>'     the exact string passed to alert()

    After calling this, trigger the button click, then call
    get_intercepted_alert(driver) to retrieve the captured message.

    Parameters
    ----------
    driver : active WebDriver instance (must already be on the target page)
    """
    driver.execute_script("""
        sessionStorage.removeItem('__alertFired');
        sessionStorage.removeItem('__alertText');
        window.alert = function(message) {
            sessionStorage.setItem('__alertText',  message);
            sessionStorage.setItem('__alertFired', '1');
        };
    """)


def get_intercepted_alert(driver, timeout=15):
    """
    Waits for the JS alert shim (installed by intercept_next_alert) to
    capture a message via sessionStorage, then returns that message.

    sessionStorage persists across location.reload() within the same tab,
    so this works regardless of whether the page reloaded before polling
    began. Polls every 500ms via WebDriverWait.

    Parameters
    ----------
    driver  : active WebDriver instance
    timeout : max seconds to wait for the alert to fire (default 15)

    Returns
    -------
    str — the message that was passed to window.alert()
    """
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            "return sessionStorage.getItem('__alertFired') === '1';"
        )
    )
    text = driver.execute_script("return sessionStorage.getItem('__alertText');") or ""
    # Clean up so stale values don’t bleed into the next interceptor call
    driver.execute_script("""
        sessionStorage.removeItem('__alertFired');
        sessionStorage.removeItem('__alertText');
    """)
    return text


def accept_alert(driver, timeout=15):
    """
    Waits for a native browser alert to appear, captures its message,
    and dismisses it by clicking OK.

    The Issue Book and Return Book buttons fire an alert via window.alert()
    after the AJAX call completes. Selenium blocks all further interactions
    until the alert is handled.

    Headless Chrome can suppress window.alert() with the console warning:
      "window.alert() dialog was suppressed because another browser modal
       dialog was already showing"
    To prevent this, we always confirm the alert is fully gone and the page
    is back to a stable document.readyState before returning.

    Parameters
    ----------
    driver  : active WebDriver instance
    timeout : max seconds to wait for the alert (default 15)

    Returns
    -------
    str — the text shown inside the alert dialog
    """
    wait = WebDriverWait(driver, timeout)
    alert = wait.until(EC.alert_is_present())
    text = alert.text
    alert.accept()
    # Wait until the alert dialog is completely dismissed.
    # This is critical in headless Chrome: if we proceed while the alert is
    # still in the browser's modal stack, the *next* alert gets suppressed.
    wait.until_not(EC.alert_is_present())
    return text


def wait_for_page_ready(driver, timeout=15):
    """
    Waits until the browser's document.readyState is 'complete'.

    Call this after accept_alert() when a success path triggers location.reload().
    Without this synchronization, find_element() calls can race against the
    ongoing page load and produce StaleElementReference or NoSuchElement errors.

    Parameters
    ----------
    driver  : active WebDriver instance
    timeout : max seconds to wait (default 15)
    """
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def dismiss_any_stray_alert(driver):
    """
    Silently dismisses any alert that may be open without raising an exception.

    Used in test teardown and before starting new interactions to prevent
    the "dialog already showing" suppression in headless Chrome.

    Parameters
    ----------
    driver : active WebDriver instance
    """
    try:
        driver.switch_to.alert.dismiss()
    except Exception:
        pass  # No alert present — that's fine


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FIXTURES
# These wrap the helpers above as pytest fixtures so tests can request
# a pre-logged-in browser directly, without repeating login steps.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def admin_driver(driver):
    """
    A browser fixture that is already logged in as Admin.

    Usage in a test:
        def test_something(admin_driver):
            # admin_driver is on /admin_dashboard, ready to use
    """
    login_as_admin(driver)
    yield driver
    # driver.quit() is handled by the parent `driver` fixture


@pytest.fixture(scope="function")
def user_driver(driver):
    """
    A browser fixture that is already logged in as a User.

    Usage in a test:
        def test_something(user_driver):
            # user_driver is on /user_dashboard, ready to use
    """
    login_as_user(driver)
    # Wait for the dashboard to be fully rendered before handing control
    # to the test. In headless mode the page can be structurally loaded
    # (URL matches) before all JS and DOM elements are interactive.
    wait_for_page_ready(driver)
    yield driver
    # driver.quit() is handled by the parent `driver` fixture
