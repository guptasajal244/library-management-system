# tests/test_issue_return.py
#
# PURPOSE:
#   Tests for the User "Issue Book" and "Return Book" workflows.
#   These workflows use AJAX (fetch API) + window.alert() dialogs — which is
#   different from normal form submissions. Selenium must handle the alert
#   before it can interact with the page again.
#
# HOW TO RUN:
#   pytest tests/test_issue_return.py -v
#   pytest -m "user or ajax" -v
#
# PREREQUISITES:
#   Flask app must be running:  python app.py
#   Credentials must be set in conftest.py
#
# ─────────────────────────────────────────────────────────────────────────────
# AJAX + ALERT FLOW (important to understand before reading the tests)
# ─────────────────────────────────────────────────────────────────────────────
#
# When the user clicks "Issue" or "Return":
#   1. JavaScript calls fetch() to POST to the Flask endpoint
#   2. Flask returns JSON: {"success": true/false, "message": "..."}
#   3. JavaScript calls window.alert() with the result message
#   4. On success, JavaScript then calls location.reload() to refresh the page
#
# Selenium behaviour:
#   - The browser freezes until the alert is dismissed (alert.accept())
#   - After accept(), if success, location.reload() fires automatically
#   - We must wait for the page to fully reload before asserting anything
#
# The accept_alert() helper in conftest.py handles steps above:
#   alert_text = accept_alert(driver)   ← dismisses alert, returns its text
#
# ─────────────────────────────────────────────────────────────────────────────
# TEST DATA STRATEGY
# ─────────────────────────────────────────────────────────────────────────────
#
# These tests need a real book in the database to issue.
# The `ensure_test_book` fixture (below) runs once per module:
#   - Spins up a temporary admin browser session
#   - Adds a book with a fixed ISBN ("ISSUE-TEST-BOOK")
#   - If the book already exists, the "already exists" message is accepted
#     gracefully — the book is still there and usable
#   - Quits the admin browser
#
# Using a fixed ISBN (not random) is intentional here:
#   - The return test depends on a book that was just issued in this run
#   - A fixed ISBN makes the three tests share a known, stable target
#   - The fixture is idempotent: running it again has no harmful effect
#
# ─────────────────────────────────────────────────────────────────────────────
# TEST ORDERING NOTE
# ─────────────────────────────────────────────────────────────────────────────
#
# These three tests model a real user workflow and intentionally run in order:
#   Test 1 → Issues the book    (state: book is now held by user)
#   Test 2 → Tries to issue it again (state: unchanged, duplicate rejected)
#   Test 3 → Returns the book   (state: book no longer held by user)
#
# pytest runs tests in file order by default, so no ordering plugin is needed.
# Do not rearrange the tests in this file.
#
# ─────────────────────────────────────────────────────────────────────────────

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from app import app, db, Book, User, IssuedBooks

# Import helpers from conftest.py.
# Fixtures (user_driver) are picked up automatically by pytest — no import.
from tests.conftest import (
    go_to,
    login_as_admin,
    accept_alert,           # kept for reference; not used by AJAX tests
    intercept_next_alert,   # JS shim: overrides window.alert() before click
    get_intercepted_alert,  # polls JS variable set by the shim
    wait_for_page_ready,
    dismiss_any_stray_alert,
)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANT: the ISBN of the book used across all three tests in this module
# ─────────────────────────────────────────────────────────────────────────────

TEST_BOOK_ISBN = "ISSUE-TEST-BOOK"


# ─────────────────────────────────────────────────────────────────────────────
# MODULE FIXTURE: ensure the test book exists before any test runs
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def ensure_test_book():
    """
    Runs ONCE before any test in this module.

    Spins up a dedicated admin browser, adds the test book, then quits.
    If the book already exists in the DB (e.g. from a previous run), the
    duplicate error is silently accepted — the book is still there and usable.

    scope="module" means this fixture runs once for the whole file, not once
    per test. autouse=True means every test gets it automatically without
    listing it as a parameter.
    """
    # ── Reset test data state in the database first ────────────────────────
    with app.app_context():
        # Find user sajal
        user = User.query.filter_by(username="sajal").first()
        if user:
            # Delete any existing issue records for the test book
            IssuedBooks.query.filter_by(user_id=user.id, isbn=TEST_BOOK_ISBN).delete()
            # Recalculate issued books count
            user.issued_books = IssuedBooks.query.filter_by(user_id=user.id).count()
        # Find the test book and make sure it has quantity 5 (if it exists)
        book = Book.query.filter_by(isbn=TEST_BOOK_ISBN).first()
        if book:
            book.quantity = 5
        db.session.commit()

    # ── Start a temporary browser for admin setup ──────────────────────────
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    
    # Enable headless mode if running in CI (GitHub Actions) or if HEADLESS env var is set
    import os
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("HEADLESS") == "true":
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-backgrounding-occluded-windows")

    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    setup_driver = webdriver.Chrome(service=service, options=options)
    setup_driver.implicitly_wait(5)
    setup_driver.maximize_window()

    try:
        # Log in as Admin and navigate to Add Book
        login_as_admin(setup_driver)
        go_to(setup_driver, "/add_book")

        # Wait for the form to load
        WebDriverWait(setup_driver, 10).until(
            EC.presence_of_element_located((By.ID, "bookISBN"))
        )

        # Fill the form with our fixed test book details
        setup_driver.find_element(By.ID, "bookISBN").send_keys(TEST_BOOK_ISBN)
        setup_driver.find_element(By.ID, "bookTitle").send_keys("Issue Return Test Book")
        setup_driver.find_element(By.ID, "bookAuthor").send_keys("Automation Author")
        setup_driver.find_element(By.ID, "bookGenre").send_keys("Test Genre")
        setup_driver.find_element(By.ID, "bookQuantity").send_keys("5")

        # Submit and wait for the server response message
        setup_driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(setup_driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".success, .error-message"))
        )

        # Read the message — both "added successfully" and "already exists" are fine.
        # Either way, the book is in the DB and ready for the tests.
        msg = setup_driver.find_element(By.CSS_SELECTOR, ".success, .error-message").text
        assert "Book added successfully!" in msg or "already exists" in msg, (
            f"Unexpected response when setting up test book: '{msg}'"
        )

    finally:
        # Always quit the setup browser, even if something went wrong above
        setup_driver.quit()

    # Hand control to the tests — no value to yield since tests use user_driver
    yield


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPER: find and click a book's Issue button by ISBN
# ─────────────────────────────────────────────────────────────────────────────

def click_issue_button(driver, isbn):
    """
    On the /search page, finds the Issue button in the row matching `isbn`
    and clicks it.

    Uses XPath to locate the <button class="issue-button"> in the same <tr>
    as the cell whose text exactly matches the ISBN.

    Parameters
    ----------
    driver : active WebDriver (must be on /search page)
    isbn   : the ISBN string to look for in the table
    """
    # Wait until the javascript handler is defined on the window
    WebDriverWait(driver, 10).until(
        lambda d: d.execute_script("return typeof issueBook === 'function';")
    )
    # XPath breakdown:
    #   //td[normalize-space()='ISBN']   → find a <td> whose text is the ISBN
    #   /ancestor::tr                    → go up to the containing <tr>
    #   //button[@class='issue-button']  → find the Issue button inside that row
    issue_btn = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((
            By.XPATH,
            f"//td[normalize-space()='{isbn}']/ancestor::tr//button[@class='issue-button']"
        ))
    )
    driver.execute_script("arguments[0].click();", issue_btn)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPER: find and click a book's Return button by ISBN
# ─────────────────────────────────────────────────────────────────────────────

def click_return_button(driver, isbn):
    """
    On the /return_book page, finds the Return button in the row matching
    `isbn` and clicks it.

    Parameters
    ----------
    driver : active WebDriver (must be on /return_book page)
    isbn   : the ISBN string to look for in the table
    """
    # Wait until the javascript handler is defined on the window
    WebDriverWait(driver, 10).until(
        lambda d: d.execute_script("return typeof returnBook === 'function';")
    )
    return_btn = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((
            By.XPATH,
            f"//td[normalize-space()='{isbn}']/ancestor::tr//button[@class='return-button']"
        ))
    )
    driver.execute_script("arguments[0].click();", return_btn)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPER: wait for the page to fully reload after a successful AJAX action
# ─────────────────────────────────────────────────────────────────────────────

def wait_for_table_reload(driver, table_id, timeout=15):
    """
    After a successful Issue or Return, JavaScript calls location.reload().
    This function waits until the table on the reloaded page is visible again.

    Without this wait, the next find_element() call could happen while the
    browser is still in the middle of reloading, causing a StaleElementReference
    or NoSuchElement exception.

    Parameters
    ----------
    driver   : active WebDriver
    table_id : the `id` attribute of the <main> table wrapper on the page
               e.g. "book_table" for /search, "return_table" for /return_book
    timeout  : max seconds to wait (default 15 — reload can be slow)
    """
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, table_id))
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Issue an available book successfully
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.user
@pytest.mark.ajax
def test_issue_book_success(user_driver):
    """
    A logged-in user can issue an available book.

    Steps:
      1. Navigate to /search (the book catalogue)
      2. Install the JS alert interceptor (BEFORE clicking — see below)
      3. Find the row for TEST_BOOK_ISBN and click its "Issue" button
      4. Collect the intercepted alert message (no native dialog involved)
      5. Assert the alert says "Book issued successfully!"
      6. Wait for location.reload() to finish
      7. Navigate to /return_book and assert the book now appears there

    Uses user_driver fixture — already logged in as User on /user_dashboard.

    WHY intercept_next_alert() instead of accept_alert():
      In headless Chrome, window.alert() can be silently suppressed if
      Chrome’s internal modal stack is not perfectly empty. The interceptor
      replaces window.alert() with a JS function that stores the message in
      a variable — no native dialog is created, so suppression is impossible.
    """
    # Step 1: Go to the search / book catalogue page
    go_to(user_driver, "/search")
    wait_for_table_reload(user_driver, "book_table")

    # Step 2: Install the JS alert shim BEFORE clicking.
    # The shim replaces window.alert() on the current page so that when
    # script.js calls alert('Book issued successfully!') after the AJAX
    # response, the message is captured in window.__alertText instead of
    # opening a native browser dialog that headless Chrome might suppress.
    intercept_next_alert(user_driver)

    # Snapshot the page element BEFORE clicking for reliable staleness detection
    old_page = user_driver.find_element(By.TAG_NAME, "html")

    # Step 3: Click the Issue button for our test book
    click_issue_button(user_driver, TEST_BOOK_ISBN)

    # Step 4: Wait for the JS shim to capture the alert message.
    # get_intercepted_alert() polls window.__alertFired — no native dialog
    # means no suppression risk whatsoever.
    try:
        alert_text = get_intercepted_alert(user_driver)
    except Exception as e:
        print("\n=== DEBUG: test_issue_book_success failed ===")
        print("Current URL:", user_driver.current_url)
        print("Console logs:")
        for entry in user_driver.get_log('browser'):
            print(entry)
        raise e

    # ── Assertion 1: Alert says the book was issued successfully
    assert "Book issued successfully!" in alert_text, (
        f"Expected success alert, got: '{alert_text}'"
    )

    # Step 5: After a successful issue, script.js calls location.reload().
    # Wait for staleness (reload started) then document.readyState==complete
    # (reload finished) before interacting with the page again.
    WebDriverWait(user_driver, 15).until(EC.staleness_of(old_page))
    wait_for_page_ready(user_driver)
    wait_for_table_reload(user_driver, "book_table")

    # ── Assertion 2: The book now appears on the /return_book page
    go_to(user_driver, "/return_book")
    wait_for_table_reload(user_driver, "return_table")

    issued_row = user_driver.find_element(
        By.XPATH,
        f"//td[normalize-space()='{TEST_BOOK_ISBN}']"
    )
    assert issued_row.is_displayed(), (
        f"Expected ISBN {TEST_BOOK_ISBN} to appear in /return_book table after issuing"
    )

    print(f"\n[PASS] Book issued successfully - ISBN: {TEST_BOOK_ISBN}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Attempt to issue the same book a second time (duplicate guard)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.user
@pytest.mark.ajax
def test_issue_book_duplicate(user_driver):
    """
    Issuing the same book a second time is rejected with an alert.

    The book was issued in test_issue_book_success (Test 1).
    This test verifies the backend and frontend guard against duplicates.

    Steps:
      1. Navigate to /search
      2. Install the JS alert interceptor
      3. Click Issue for TEST_BOOK_ISBN (book already held by this user)
      4. Collect the intercepted alert message
      5. Assert the alert contains the duplicate warning
      6. Assert the book appears exactly once on /return_book

    NOTE: This test depends on Test 1 having run first in this session.
    """
    # Step 1: Go to the search page
    go_to(user_driver, "/search")
    wait_for_table_reload(user_driver, "book_table")

    # Step 2: Install the JS alert shim BEFORE clicking.
    # On a duplicate issue, script.js calls alert('Book already issued...')
    # without calling location.reload() afterward. The shim captures the
    # message so we can assert on it without any native dialog.
    intercept_next_alert(user_driver)

    # Step 3: Click Issue again for the same book
    click_issue_button(user_driver, TEST_BOOK_ISBN)

    # Step 4: Collect the intercepted message.
    # No location.reload() fires on failure, so no staleness check needed.
    try:
        alert_text = get_intercepted_alert(user_driver)
    except Exception as e:
        print("\n=== DEBUG: test_issue_book_duplicate failed ===")
        print("Current URL:", user_driver.current_url)
        print("Console logs:")
        for entry in user_driver.get_log('browser'):
            print(entry)
        raise e

    # ── Assertion 1: Alert contains the duplicate-issue warning
    assert "already issued" in alert_text, (
        f"Expected 'already issued' in alert, got: '{alert_text}'"
    )

    # ── Assertion 2: Still on /search (no reload on failure)
    assert "/search" in user_driver.current_url, (
        f"Expected to stay on /search after duplicate issue, got: {user_driver.current_url}"
    )

    # ── Assertion 3: The book appears exactly once on /return_book
    go_to(user_driver, "/return_book")
    wait_for_table_reload(user_driver, "return_table")

    isbn_cells = user_driver.find_elements(
        By.XPATH,
        f"//td[normalize-space()='{TEST_BOOK_ISBN}']"
    )
    assert len(isbn_cells) == 1, (
        f"Expected exactly 1 row for ISBN {TEST_BOOK_ISBN} in /return_book, "
        f"found {len(isbn_cells)}"
    )

    print(f"\n[PASS] Duplicate issue correctly rejected - ISBN: {TEST_BOOK_ISBN}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Return an issued book successfully
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.user
@pytest.mark.ajax
def test_return_book_success(user_driver):
    """
    A logged-in user can return a book they have currently issued.

    Steps:
      1. Navigate to /return_book
      2. Verify the book is listed (setup check)
      3. Install the JS alert interceptor
      4. Click the Return button for TEST_BOOK_ISBN
      5. Collect the intercepted alert message
      6. Assert the alert says "Book returned successfully!"
      7. Wait for location.reload() to finish
      8. Assert the returned book is NO LONGER in /return_book
      9. Assert book quantity > 0 on /search

    NOTE: This test depends on Test 1 having issued the book first.
    """
    # Step 1: Go to the return book page
    go_to(user_driver, "/return_book")
    wait_for_table_reload(user_driver, "return_table")

    # Step 2: Verify the book is present before attempting the return.
    pre_return_rows = user_driver.find_elements(
        By.XPATH,
        f"//td[normalize-space()='{TEST_BOOK_ISBN}']"
    )
    assert len(pre_return_rows) == 1, (
        f"Setup check failed: expected ISBN {TEST_BOOK_ISBN} in /return_book before returning. "
        "Make sure test_issue_book_success ran first in this session."
    )

    # Step 3: Install the JS alert shim BEFORE clicking.
    intercept_next_alert(user_driver)

    # Snapshot the page element BEFORE clicking for reliable staleness detection
    old_page = user_driver.find_element(By.TAG_NAME, "html")

    # Step 4: Click the Return button for our test book
    click_return_button(user_driver, TEST_BOOK_ISBN)

    # Step 5: Collect the intercepted message from the JS shim
    alert_text = get_intercepted_alert(user_driver)

    # ── Assertion 1: Alert confirms successful return
    assert "Book returned successfully!" in alert_text, (
        f"Expected return success alert, got: '{alert_text}'"
    )

    # Step 6: Wait for location.reload() to complete
    WebDriverWait(user_driver, 15).until(EC.staleness_of(old_page))
    wait_for_page_ready(user_driver)
    wait_for_table_reload(user_driver, "return_table")

    # ── Assertion 2: Book is NO LONGER listed in /return_book
    post_return_rows = user_driver.find_elements(
        By.XPATH,
        f"//td[normalize-space()='{TEST_BOOK_ISBN}']"
    )
    assert len(post_return_rows) == 0, (
        f"Expected ISBN {TEST_BOOK_ISBN} to be removed from /return_book after return, "
        f"but found {len(post_return_rows)} row(s)"
    )

    # ── Assertion 3: Book reappears on /search with quantity > 0
    go_to(user_driver, "/search")
    wait_for_table_reload(user_driver, "book_table")

    quantity_cell = user_driver.find_element(
        By.XPATH,
        f"//td[normalize-space()='{TEST_BOOK_ISBN}']/ancestor::tr/td[5]"
    )
    quantity_text = quantity_cell.text.strip()
    assert quantity_text.isdigit() and int(quantity_text) > 0, (
        f"Expected quantity > 0 in /search after return, got: '{quantity_text}'"
    )

    print(f"\n[PASS] Book returned successfully - ISBN: {TEST_BOOK_ISBN}, "
          f"quantity now: {quantity_text}")
