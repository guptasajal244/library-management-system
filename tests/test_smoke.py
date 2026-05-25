# tests/test_smoke.py
#
# PURPOSE:
#   Smoke tests verify that the Selenium setup itself is working correctly.
#   Run these first before writing any other tests.
#   If all 8 tests here pass, the environment is correctly configured.
#
# HOW TO RUN:
#   pytest tests/test_smoke.py -v
#   pytest -m smoke -v
#
# WHAT THESE TESTS CHECK:
#   1. Flask app is reachable
#   2. Landing page renders correctly
#   3. Admin login flow works end-to-end
#   4. Admin login shows error on wrong credentials
#   5. User login flow works end-to-end
#   6. User login shows error on wrong credentials
#   7. Admin logout returns to landing page
#   8. User logout returns to landing page

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# Import helpers defined in conftest.py
# (pytest makes conftest.py available automatically — no explicit import needed
#  for fixtures, but plain functions must be imported like any module)
from tests.conftest import (
    go_to,
    login_as_admin,
    login_as_user,
    BASE_URL,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    USER_USERNAME,
    USER_PASSWORD,
)


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 1
# Verify the Flask application is running and the landing page is reachable.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_landing_page_loads(driver):
    """
    The app is running and the landing page renders its heading and form.

    This is the most fundamental check — if this fails, the Flask server
    is not running or the BASE_URL is wrong.
    """
    go_to(driver, "/")

    # Wait until the page title is set before asserting on it.
    # Without this, driver.title can return '' while Chrome is still
    # rendering — causing a false failure even though the page is correct.
    WebDriverWait(driver, 10).until(EC.title_contains("Library Management System"))

    # Page title should say "Library Management System"
    assert "Library Management System" in driver.title, (
        f"Expected page title to contain 'Library Management System', got: '{driver.title}'"
    )

    # The login type dropdown must be present
    dropdown = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "loginType"))
    )
    assert dropdown.is_displayed(), "Login type dropdown is not visible on the landing page"

    # The submit button must be present
    submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    assert submit_btn.is_displayed(), "Submit button is not visible on the landing page"

    print("\n[PASS] Landing page loaded successfully")


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 2
# Verify that clicking "Admin" on the landing page navigates to /admin_login.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_landing_page_admin_redirect(driver):
    """
    Selecting 'Admin' and clicking Login redirects to the Admin Login page.
    """
    go_to(driver, "/")

    # Select "Admin" from the dropdown
    Select(driver.find_element(By.ID, "loginType")).select_by_value("admin")

    # Click Login
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Should now be on /admin_login
    WebDriverWait(driver, 10).until(EC.url_contains("/admin_login"))

    assert "/admin_login" in driver.current_url, (
        f"Expected to be on /admin_login, but got: {driver.current_url}"
    )

    # The admin username input must be visible
    assert driver.find_element(By.ID, "adminUsername").is_displayed()

    print("\n[PASS] Admin redirect from landing page works")


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 3
# Verify that clicking "User" on the landing page navigates to /user_login.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_landing_page_user_redirect(driver):
    """
    Selecting 'User' and clicking Login redirects to the User Login page.
    """
    go_to(driver, "/")

    # Select "User" from the dropdown
    Select(driver.find_element(By.ID, "loginType")).select_by_value("user")

    # Click Login
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Should now be on /user_login
    WebDriverWait(driver, 10).until(EC.url_contains("/user_login"))

    assert "/user_login" in driver.current_url, (
        f"Expected to be on /user_login, but got: {driver.current_url}"
    )

    # The user username input must be visible
    assert driver.find_element(By.ID, "userUsername").is_displayed()

    print("\n[PASS] User redirect from landing page works")


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 4
# Admin login with VALID credentials → lands on /admin_dashboard.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_admin_login_valid_credentials(driver):
    """
    Admin can log in with correct username and password.
    After login, the browser should be on /admin_dashboard.

    ⚠️  Update ADMIN_USERNAME and ADMIN_PASSWORD in conftest.py to match
        the credentials stored in your database.
    """
    login_as_admin(driver)

    # Should be on the admin dashboard
    assert "/admin_dashboard" in driver.current_url, (
        f"Login failed — expected /admin_dashboard, got: {driver.current_url}"
    )

    # The dashboard heading should be visible
    heading = driver.find_element(By.TAG_NAME, "h1")
    assert "Admin Dashboard" in heading.text, (
        f"Unexpected heading on admin dashboard: '{heading.text}'"
    )

    print(f"\n[PASS] Admin login succeeded - on: {driver.current_url}")


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 5
# Admin login with INVALID credentials → stays on /admin_login with error.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_admin_login_invalid_credentials(driver):
    """
    Admin login with wrong password shows the error message and
    does NOT redirect to /admin_dashboard.
    """
    # Use deliberately wrong credentials.
    # expect_success=False tells the helper NOT to wait for a dashboard redirect
    # (which would never happen) — it returns right after submitting the form.
    login_as_admin(driver, username="wrong_admin", password="wrong_password",
                   expect_success=False)

    # Should still be on /admin_login (not redirected)
    assert "/admin_login" in driver.current_url, (
        f"Expected to stay on /admin_login after bad credentials, got: {driver.current_url}"
    )

    # The error message paragraph should now be visible
    error_msg = driver.find_element(By.CSS_SELECTOR, ".error-message")
    assert error_msg.is_displayed(), "Error message is not displayed after wrong credentials"
    assert "Invalid" in error_msg.text, (
        f"Expected 'Invalid' in error text, got: '{error_msg.text}'"
    )

    print("\n[PASS] Admin login correctly rejected invalid credentials")


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 6
# User login with VALID credentials → lands on /user_dashboard.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_user_login_valid_credentials(driver):
    """
    A regular user can log in with correct credentials.
    After login, the browser should be on /user_dashboard.

    ⚠️  Update USER_USERNAME and USER_PASSWORD in conftest.py to match
        a real user in your database.
    """
    login_as_user(driver)

    # Should be on the user dashboard
    assert "/user_dashboard" in driver.current_url, (
        f"Login failed — expected /user_dashboard, got: {driver.current_url}"
    )

    # The dashboard should show "User Dashboard" heading
    heading = driver.find_element(By.TAG_NAME, "h1")
    assert "User Dashboard" in heading.text, (
        f"Unexpected heading on user dashboard: '{heading.text}'"
    )

    print(f"\n[PASS] User login succeeded - on: {driver.current_url}")


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 7
# User login with INVALID credentials → stays on /user_login with error.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_user_login_invalid_credentials(driver):
    """
    User login with wrong credentials shows the error message and
    does NOT redirect to /user_dashboard.
    """
    # Use deliberately wrong credentials.
    # expect_success=False tells the helper NOT to wait for a dashboard redirect
    # (which would never happen) — it returns right after submitting the form.
    login_as_user(driver, username="no_such_user", password="wrong_pass",
                  expect_success=False)

    # Should still be on /user_login
    assert "/user_login" in driver.current_url, (
        f"Expected to stay on /user_login after bad credentials, got: {driver.current_url}"
    )

    # Error message should appear
    error_msg = driver.find_element(By.CSS_SELECTOR, ".error-message")
    assert error_msg.is_displayed(), "Error message is not displayed after wrong user credentials"
    assert "Invalid" in error_msg.text, (
        f"Expected 'Invalid' in error text, got: '{error_msg.text}'"
    )

    print(f"\n[PASS] User login correctly rejected invalid credentials")


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 8
# Admin logout → redirected back to the landing page.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_admin_logout(admin_driver):
    """
    After logging in as Admin, clicking Logout returns to the landing page.

    Uses the `admin_driver` fixture (defined in conftest.py), which provides
    a browser that is already logged in as Admin.
    """
    # admin_driver is already on /admin_dashboard
    # Wait for the logout link to be clickable (not just present) before clicking.
    # In headless mode the dashboard may still be rendering when we look for it.
    wait = WebDriverWait(admin_driver, 10)
    logout_link = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='logout']"))
    )
    logout_link.click()

    # Should be back on the landing page (/ or /login)
    WebDriverWait(admin_driver, 15).until(
        lambda d: "/login" in d.current_url or d.current_url.rstrip("/").endswith(":5000")
    )

    # The login type dropdown should be visible again (we're back at landing)
    dropdown = WebDriverWait(admin_driver, 10).until(
        EC.visibility_of_element_located((By.ID, "loginType"))
    )
    assert dropdown.is_displayed(), "After logout, expected to see the login dropdown"

    print(f"\n[PASS] Admin logout works - returned to: {admin_driver.current_url}")


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST 9
# User logout → redirected back to the landing page.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_user_logout(user_driver):
    """
    After logging in as a User, clicking Logout returns to the landing page.

    Uses the `user_driver` fixture (defined in conftest.py), which provides
    a browser that is already logged in as a User.
    """
    # user_driver is already on /user_dashboard
    # Wait for the logout link to be clickable (not just present) before clicking.
    # In headless mode the dashboard may still be rendering when we look for it.
    wait = WebDriverWait(user_driver, 10)
    logout_link = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='logout']"))
    )
    logout_link.click()

    # Should be back on the landing page (/login or /)
    WebDriverWait(user_driver, 15).until(
        lambda d: "/login" in d.current_url or d.current_url.rstrip("/").endswith(":5000")
    )

    # Login dropdown should be visible — confirms landing page fully rendered
    dropdown = WebDriverWait(user_driver, 10).until(
        EC.visibility_of_element_located((By.ID, "loginType"))
    )
    assert dropdown.is_displayed(), (
        f"Expected redirect to login page after logout, got: {user_driver.current_url}"
    )

    print(f"\n[PASS] User logout works - returned to: {user_driver.current_url}")
