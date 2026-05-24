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

    # ── Uncomment the line below to run headless (no visible browser window)
    # options.add_argument("--headless=new")

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
# HELPER: dismiss a browser alert and return its text
# Used by issue_book and return_book tests (AJAX + window.alert flow)
# ─────────────────────────────────────────────────────────────────────────────

def accept_alert(driver, timeout=10):
    """
    Waits for a native browser alert to appear, captures its message,
    and dismisses it by clicking OK.

    The Issue Book and Return Book buttons fire an alert via window.alert()
    after the AJAX call completes. Selenium blocks all further interactions
    until the alert is handled.

    Parameters
    ----------
    driver  : active WebDriver instance
    timeout : max seconds to wait for the alert (default 10)

    Returns
    -------
    str — the text shown inside the alert dialog
    """
    wait = WebDriverWait(driver, timeout)
    alert = wait.until(EC.alert_is_present())
    text = alert.text
    alert.accept()
    return text


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
    yield driver
    # driver.quit() is handled by the parent `driver` fixture
