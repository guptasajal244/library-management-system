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

# Import helpers from conftest.py.
# Fixtures (user_driver) are picked up automatically by pytest — no import.
from tests.conftest import (
    go_to,
    login_as_admin,
    accept_alert,
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
    # ── Start a temporary browser for admin setup ──────────────────────────
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
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
    # XPath breakdown:
    #   //td[normalize-space()='ISBN']   → find a <td> whose text is the ISBN
    #   /ancestor::tr                    → go up to the containing <tr>
    #   //button[@class='issue-button']  → find the Issue button inside that row
    issue_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((
            By.XPATH,
            f"//td[normalize-space()='{isbn}']/ancestor::tr//button[@class='issue-button']"
        ))
    )
    issue_btn.click()


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
    return_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((
            By.XPATH,
            f"//td[normalize-space()='{isbn}']/ancestor::tr//button[@class='return-button']"
        ))
    )
    return_btn.click()


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
      2. Find the row for TEST_BOOK_ISBN and click its "Issue" button
      3. An alert fires — accept it and capture its text
      4. Assert the alert says "Book issued successfully!"
      5. Wait for the page to reload (location.reload() fires after alert)
      6. Navigate to /return_book and assert the book now appears there

    Uses user_driver fixture — already logged in as User on /user_dashboard.
    """
    # Step 1: Go to the search / book catalogue page
    go_to(user_driver, "/search")

    # Wait for the book table to load before looking for the row
    wait_for_table_reload(user_driver, "book_table")

    # Step 2: Click the Issue button for our test book
    click_issue_button(user_driver, TEST_BOOK_ISBN)

    # Step 3: The AJAX call fires and JavaScript shows a window.alert().
    # accept_alert() waits for the alert, captures its text, and dismisses it.
    alert_text = accept_alert(user_driver)

    # ── Assertion 1: Alert says the book was issued successfully
    # (from script.js: alert('Book issued successfully!'))
    assert "Book issued successfully!" in alert_text, (
        f"Expected success alert, got: '{alert_text}'"
    )

    # Step 4: After a successful issue, JavaScript calls location.reload().
    # We must wait for the table to reappear before doing anything else.
    wait_for_table_reload(user_driver, "book_table")

    # ── Assertion 2: The book now appears on the /return_book page
    # This confirms the DB was actually updated — not just that the alert fired.
    go_to(user_driver, "/return_book")
    wait_for_table_reload(user_driver, "return_table")

    # The test book's ISBN must now be visible in the "Books Issued by You" table
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
      2. Click Issue for TEST_BOOK_ISBN (book already held by this user)
      3. An alert fires — accept it and capture its text
      4. Assert the alert contains the duplicate warning
      5. Assert the book is NOT added a second time to /return_book
         (it should appear exactly once)

    NOTE: This test depends on Test 1 having run first in this session.
    If Test 1 didn't run (e.g. you run this test in isolation), the book
    will not be issued and this test will see a success alert instead.
    """
    # Step 1: Go to the search page
    go_to(user_driver, "/search")
    wait_for_table_reload(user_driver, "book_table")

    # Step 2: Click Issue again for the same book
    click_issue_button(user_driver, TEST_BOOK_ISBN)

    # Step 3: Accept the alert and capture its message
    alert_text = accept_alert(user_driver)

    # ── Assertion 1: Alert contains the duplicate-issue warning
    # (from script.js: alert('Book already issued. You cannot issue multiple copies.'))
    assert "already issued" in alert_text, (
        f"Expected 'already issued' in alert, got: '{alert_text}'"
    )

    # ── Assertion 2: The page did NOT reload (no location.reload() on failure)
    # We're still on /search — confirm the URL
    assert "/search" in user_driver.current_url, (
        f"Expected to stay on /search after duplicate issue, got: {user_driver.current_url}"
    )

    # ── Assertion 3: The book appears exactly once on /return_book
    # (not added a second time despite the duplicate attempt)
    go_to(user_driver, "/return_book")
    wait_for_table_reload(user_driver, "return_table")

    # Count how many rows contain our ISBN
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
      2. Find the row for TEST_BOOK_ISBN and click its "Return" button
      3. An alert fires — accept it and capture its text
      4. Assert the alert says "Book returned successfully!"
      5. Wait for the page to reload
      6. Assert the returned book is NO LONGER listed in /return_book
      7. Navigate to /search and assert the book's quantity increased

    NOTE: This test depends on Test 1 having issued the book first.
    """
    # Step 1: Go to the return book page
    go_to(user_driver, "/return_book")

    # Wait for the table of issued books to load
    wait_for_table_reload(user_driver, "return_table")

    # Verify the book is present before attempting the return.
    # If this assertion fails, Test 1 did not run in this session.
    pre_return_rows = user_driver.find_elements(
        By.XPATH,
        f"//td[normalize-space()='{TEST_BOOK_ISBN}']"
    )
    assert len(pre_return_rows) == 1, (
        f"Setup check failed: expected ISBN {TEST_BOOK_ISBN} in /return_book before returning. "
        "Make sure test_issue_book_success ran first in this session."
    )

    # Step 2: Click the Return button for our test book
    click_return_button(user_driver, TEST_BOOK_ISBN)

    # Step 3: Accept the alert from the AJAX return call
    alert_text = accept_alert(user_driver)

    # ── Assertion 1: Alert confirms successful return
    # (from script.js: alert('Book returned successfully!'))
    assert "Book returned successfully!" in alert_text, (
        f"Expected return success alert, got: '{alert_text}'"
    )

    # Step 4: Wait for the page to reload (location.reload() fires after success)
    wait_for_table_reload(user_driver, "return_table")

    # ── Assertion 2: The book is NO LONGER listed in /return_book
    # After a successful return, the row should be gone from this table.
    post_return_rows = user_driver.find_elements(
        By.XPATH,
        f"//td[normalize-space()='{TEST_BOOK_ISBN}']"
    )
    assert len(post_return_rows) == 0, (
        f"Expected ISBN {TEST_BOOK_ISBN} to be removed from /return_book after return, "
        f"but found {len(post_return_rows)} row(s)"
    )

    # ── Assertion 3: The book reappears on /search with quantity > 0
    # This confirms the DB was updated — the returned copy was added back.
    go_to(user_driver, "/search")
    wait_for_table_reload(user_driver, "book_table")

    # Find the quantity cell in the same row as our ISBN
    quantity_cell = user_driver.find_element(
        By.XPATH,
        f"//td[normalize-space()='{TEST_BOOK_ISBN}']/ancestor::tr/td[5]"
        #                                                              ^^^
        # Column 5 is Quantity in search.html: ISBN | Title | Author | Genre | Quantity | Issue
    )
    quantity_text = quantity_cell.text.strip()
    assert quantity_text.isdigit() and int(quantity_text) > 0, (
        f"Expected quantity > 0 in /search after return, got: '{quantity_text}'"
    )

    print(f"\n[PASS] Book returned successfully - ISBN: {TEST_BOOK_ISBN}, "
          f"quantity now: {quantity_text}")
