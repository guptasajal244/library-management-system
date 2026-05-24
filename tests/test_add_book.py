# tests/test_add_book.py
#
# PURPOSE:
#   Tests for the Admin "Add Book" workflow (/add_book).
#   Covers the three main outcomes the backend can produce:
#     1. Successful book creation
#     2. Duplicate ISBN rejection
#     3. Invalid quantity rejection
#
# HOW TO RUN:
#   pytest tests/test_add_book.py -v
#   pytest -m admin -v          ← runs all admin-tagged tests
#
# PREREQUISITES:
#   Flask app must be running:  python app.py
#   Admin credentials must be set in conftest.py
#
# ─────────────────────────────────────────────────────────────────────────────
# HOW DYNAMIC ISBNs WORK
# ─────────────────────────────────────────────────────────────────────────────
# Each test run generates a fresh ISBN using uuid4(), so tests never conflict
# with data left behind by a previous run.
#
# Example generated ISBN:  "TEST-a3f2b1c0"
#
# The "TEST-" prefix makes it easy to identify and clean up automation-created
# records in the database if needed.
# ─────────────────────────────────────────────────────────────────────────────

import uuid
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import the navigation helper from conftest.py.
# The `admin_driver` fixture is picked up automatically by pytest — no import needed.
from tests.conftest import go_to


# ─────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL HELPER: generate a unique ISBN for this test run
# ─────────────────────────────────────────────────────────────────────────────

def make_isbn():
    """
    Returns a unique ISBN string guaranteed not to collide with any previous
    test run.

    Format: "TEST-<first 8 hex chars of a UUID>"
    Example: "TEST-a3f2b1c0"

    Using uuid4() (random UUID) makes collisions statistically impossible.
    The "TEST-" prefix lets you filter automation records in the DB easily.
    """
    return "TEST-" + uuid.uuid4().hex[:8]


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPER: navigate to /add_book and fill the form
# ─────────────────────────────────────────────────────────────────────────────

def fill_add_book_form(driver, isbn, title, author, genre, quantity):
    """
    Navigates to the Add Book page and fills every field.
    Does NOT click Submit — the calling test does that so it can assert
    before and after the click as needed.

    Parameters
    ----------
    driver   : active WebDriver (must already be logged in as Admin)
    isbn     : string to type into #bookISBN
    title    : string to type into #bookTitle
    author   : string to type into #bookAuthor
    genre    : string to type into #bookGenre
    quantity : string to type into #bookQuantity (intentionally a string so
               we can also pass invalid values like "0" or "-5")
    """
    # Navigate directly to the Add Book page.
    # admin_driver is already authenticated, so this won't redirect to /login.
    go_to(driver, "/add_book")

    # Wait until the ISBN field is present before interacting.
    # (Protects against slow page loads.)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "bookISBN"))
    )

    # Fill each form field using its stable `id` attribute.
    driver.find_element(By.ID, "bookISBN").send_keys(isbn)
    driver.find_element(By.ID, "bookTitle").send_keys(title)
    driver.find_element(By.ID, "bookAuthor").send_keys(author)
    driver.find_element(By.ID, "bookGenre").send_keys(genre)
    driver.find_element(By.ID, "bookQuantity").send_keys(quantity)


def submit_form(driver):
    """
    Clicks the 'Add Book' submit button and waits for the page to respond.

    The form posts to itself (action="#"), so the URL stays at /add_book.
    We wait for the <p class="success"> message element to appear, which
    signals that the server has processed the submission and re-rendered
    the page with a result message.
    """
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Wait until the success/error message paragraph appears.
    # The template only renders <p class="success"> when success_message is set,
    # which happens only after a POST — so its presence confirms the form was
    # submitted and the server responded.
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
    (
        By.CSS_SELECTOR,
        ".success, .error-message"
    )
)
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Add a valid new book successfully
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.admin
def test_add_book_valid(admin_driver):
    """
    Adding a book with all valid fields shows "Book added successfully!".

    Steps:
      1. Navigate to /add_book
      2. Fill the form with valid data and a unique ISBN
      3. Click "Add Book"
      4. Assert the success message appears with correct text
      5. Assert we are still on /add_book (form self-posts)

    Uses admin_driver fixture → already logged in as Admin on /admin_dashboard.
    """
    # Generate a unique ISBN so this test never conflicts with previous runs.
    unique_isbn = make_isbn()

    # Fill the form with valid data.
    fill_add_book_form(
        admin_driver,
        isbn=unique_isbn,
        title="Selenium Testing Guide",
        author="Jane Doe",
        genre="Technology",
        quantity="3",           # valid positive integer
    )

    # Click Submit and wait for the result message.
    submit_form(admin_driver)

    # ── Assertion 1: The page still shows /add_book (no redirect on success)
    assert "/add_book" in admin_driver.current_url, (
        f"Expected to stay on /add_book after submission, got: {admin_driver.current_url}"
    )

    # ── Assertion 2: The success message paragraph is visible
    message_element = admin_driver.find_element(By.CSS_SELECTOR, ".success, .error-message")
    assert message_element.is_displayed(), (
        "Expected the success message to be visible after adding a book"
    )

    # ── Assertion 3: The message text matches exactly what the server sends
    # (from app.py line 243: success_message = 'Book added successfully!')
    assert "Book added successfully!" in message_element.text, (
        f"Unexpected message text: '{message_element.text}'"
    )

    print(f"\n[PASS] Book added successfully with ISBN: {unique_isbn}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Add a book with a duplicate ISBN and verify error handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.admin
def test_add_book_duplicate_isbn(admin_driver):
    """
    Submitting the same ISBN twice shows the duplicate-ISBN error message.

    The app checks for ISBN uniqueness before inserting (app.py line 233).
    If the ISBN already exists, it returns:
      "Book with the provided ISBN already exists. Please use a unique ISBN."

    Steps:
      1. Add a book with a unique ISBN (first submission — should succeed)
      2. Try to add another book with the SAME ISBN (second submission)
      3. Assert the duplicate-ISBN error message appears
    """
    # One unique ISBN shared across both submissions in this test.
    duplicate_isbn = make_isbn()

    # ── First submission: add the book successfully ──────────────────────────
    fill_add_book_form(
        admin_driver,
        isbn=duplicate_isbn,
        title="First Book",
        author="Author One",
        genre="Fiction",
        quantity="2",
    )
    submit_form(admin_driver)

    # Sanity check: first submission must have succeeded before we test the
    # duplicate path. If this fails, the test data or credentials are wrong.
    first_message = admin_driver.find_element(By.CSS_SELECTOR, ".success, .error-message").text
    assert "Book added successfully!" in first_message, (
        f"Setup failed — first submission did not succeed. Got: '{first_message}'"
    )

    # ── Second submission: attempt the same ISBN again ───────────────────────
    # Navigate back to a fresh /add_book form.
    # (The page already shows /add_book after the first submit, but navigating
    #  again gives us a clean form with no pre-filled values.)
    fill_add_book_form(
        admin_driver,
        isbn=duplicate_isbn,          # same ISBN — this should be rejected
        title="Duplicate Book",
        author="Author Two",
        genre="Science",
        quantity="1",
    )
    submit_form(admin_driver)

    # ── Assertion 1: Still on /add_book (no redirect)
    assert "/add_book" in admin_driver.current_url, (
        f"Expected to stay on /add_book after duplicate submission, got: {admin_driver.current_url}"
    )

    # ── Assertion 2: The error message is displayed
    error_element = admin_driver.find_element(By.CSS_SELECTOR, ".success, .error-message")
    assert error_element.is_displayed(), (
        "Expected an error message to appear after submitting a duplicate ISBN"
    )

    # ── Assertion 3: The message text matches the duplicate-ISBN server response
    # (from app.py line 234)
    assert "Book with the provided ISBN already exists" in error_element.text, (
        f"Expected duplicate-ISBN error, got: '{error_element.text}'"
    )

    print(f"\n[PASS] Duplicate ISBN correctly rejected - ISBN: {duplicate_isbn}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Add a book with invalid quantity and verify backend validation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.admin
@pytest.mark.parametrize("bad_quantity, description", [
    ("0",    "zero"),
    ("-5",   "negative number"),
    ("abc",  "non-numeric text"),
])
def test_add_book_invalid_quantity(admin_driver, bad_quantity, description):
    """
    Submitting a book with an invalid quantity shows the validation error.

    The backend validates quantity before touching the database (app.py line 224):
      - Rejects zero
      - Rejects negative numbers
      - Rejects non-numeric strings
    All three cases produce: "Error: Quantity must be a positive whole number."

    This test is parametrized: it runs once for each invalid value above,
    giving us three separate test cases from one function.

    Parameters
    ----------
    bad_quantity  : the invalid value to type into #bookQuantity
    description   : human-readable label shown in the test ID
    """
    # Use a unique ISBN for each parametrized run so there are no cross-run
    # conflicts (even though invalid-quantity submissions never reach the DB).
    unique_isbn = make_isbn()

    fill_add_book_form(
        admin_driver,
        isbn=unique_isbn,
        title="Invalid Quantity Book",
        author="Test Author",
        genre="Drama",
        quantity=bad_quantity,    # the invalid value being tested
    )
    submit_form(admin_driver)

    # ── Assertion 1: Still on /add_book (backend rejects and re-renders)
    assert "/add_book" in admin_driver.current_url, (
        f"Expected to stay on /add_book after invalid quantity '{bad_quantity}', "
        f"got: {admin_driver.current_url}"
    )

    # ── Assertion 2: The validation error message is displayed
    error_element = admin_driver.find_element(By.CSS_SELECTOR, ".success, .error-message")
    assert error_element.is_displayed(), (
        f"Expected a validation error message for quantity='{bad_quantity}'"
    )

    # ── Assertion 3: The message text matches the backend validation response
    # (from app.py line 229)
    assert "Error: Quantity must be a positive whole number." in error_element.text, (
        f"Unexpected message for quantity='{bad_quantity}' ({description}): "
        f"'{error_element.text}'"
    )

    print(f"\n[PASS] Invalid quantity '{bad_quantity}' ({description}) correctly rejected")
