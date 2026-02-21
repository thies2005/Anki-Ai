
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add project root to sys.path to ensure we can import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture
def mock_dependencies():
    """
    Creates mocks for all external dependencies that might be missing in the environment.
    """
    mock_pd = MagicMock()
    mock_google = MagicMock()
    mock_genai = MagicMock()
    mock_google.genai = mock_genai
    mock_openai = MagicMock()
    mock_numpy = MagicMock()
    mock_fitz = MagicMock()
    mock_tenacity = MagicMock()
    mock_requests = MagicMock()

    # Mock DataFrame behavior
    class MockDataFrame:
        def __init__(self, data):
            self.data = data # List of dicts
            self.empty = len(data) == 0

        def iterrows(self):
            for i, row in enumerate(self.data):
                yield i, row

    mock_pd.DataFrame = MockDataFrame

    return {
        "pandas": mock_pd,
        "google": mock_google,
        "google.genai": mock_genai,
        "openai": mock_openai,
        "numpy": mock_numpy,
        "fitz": mock_fitz,
        "tenacity": mock_tenacity,
        "requests": mock_requests
    }

@pytest.fixture
def data_processing_module(mock_dependencies):
    """
    Imports utils.data_processing with mocked dependencies.
    Uses patch.dict to avoid polluting the global namespace for other tests.
    """
    with patch.dict(sys.modules, mock_dependencies):
        # We need to ensure utils.data_processing is re-imported if it was already loaded
        # to pick up the mocks. However, since we are patching sys.modules,
        # if it wasn't loaded, it will use the patched modules.
        # If it WAS loaded, it might have references to real modules (if they existed).
        # In this environment, real modules don't exist, so previous import would have failed.

        # We also need to mock 'utils' package if it imports things at top level
        # But 'utils' is a package.

        if "utils.data_processing" in sys.modules:
           del sys.modules["utils.data_processing"]

        import utils.data_processing
        yield utils.data_processing

        # Cleanup is handled by patch.dict restoration of sys.modules

def test_format_cards_basic(data_processing_module):
    """Test basic card formatting with standard input."""
    # We need to access MockDataFrame from the mocked pandas module
    # But since we have the module object, we can use it.
    # Or we can reconstruct the MockDataFrame here if we export it,
    # or just use a list of dicts and MockDataFrame from the fixture?
    # The module uses pd.DataFrame, so we need to pass something that acts like it.

    # We can get the MockDataFrame class from the mocked pandas module attached to data_processing_module
    # But data_processing_module imports pandas as pd.
    MockDataFrame = data_processing_module.pd.DataFrame

    data = [
        {'Deck': 'Test Deck', 'Front': 'Q1', 'Back': 'A1', 'Tag': 'tag1'},
        {'Deck': 'Test Deck', 'Front': 'Q2', 'Back': 'A2', 'Tag': 'tag2'}
    ]
    df = MockDataFrame(data)

    notes = data_processing_module.format_cards_for_ankiconnect(df)

    assert len(notes) == 2

    # Check first note
    assert notes[0]['deckName'] == 'Test Deck'
    assert notes[0]['modelName'] == 'Basic'
    assert notes[0]['fields']['Front'] == 'Q1'
    assert notes[0]['fields']['Back'] == 'A1'
    assert notes[0]['tags'] == ['tag1']
    assert notes[0]['options']['allowDuplicate'] is False

    # Check second note
    assert notes[1]['fields']['Front'] == 'Q2'
    assert notes[1]['tags'] == ['tag2']

def test_format_cards_empty(data_processing_module):
    """Test with an empty DataFrame."""
    MockDataFrame = data_processing_module.pd.DataFrame
    df = MockDataFrame([])
    notes = data_processing_module.format_cards_for_ankiconnect(df)
    assert len(notes) == 0
    assert isinstance(notes, list)

def test_format_cards_missing_tags(data_processing_module):
    """Test handling of missing or empty tags."""
    MockDataFrame = data_processing_module.pd.DataFrame
    data = [
        {'Deck': 'Test Deck', 'Front': 'Q1', 'Back': 'A1', 'Tag': None},
        {'Deck': 'Test Deck', 'Front': 'Q2', 'Back': 'A2', 'Tag': ''},
        {'Deck': 'Test Deck', 'Front': 'Q3', 'Back': 'A3', 'Tag': False}
    ]
    df = MockDataFrame(data)

    notes = data_processing_module.format_cards_for_ankiconnect(df)

    assert len(notes) == 3
    assert notes[0]['tags'] == []
    assert notes[1]['tags'] == []
    assert notes[2]['tags'] == []

def test_format_cards_special_chars(data_processing_module):
    """Test that special characters are preserved in Front/Back fields."""
    MockDataFrame = data_processing_module.pd.DataFrame
    data = [
        {'Deck': 'Test Deck', 'Front': 'Q"1"', 'Back': 'A<1>', 'Tag': 't&g'},
        {'Deck': 'Test Deck', 'Front': 'Math: 2 + 2 = 4', 'Back': 'Result: 4', 'Tag': '#math'}
    ]
    df = MockDataFrame(data)

    notes = data_processing_module.format_cards_for_ankiconnect(df)

    assert notes[0]['fields']['Front'] == 'Q"1"'
    assert notes[0]['fields']['Back'] == 'A<1>'
    assert notes[0]['tags'] == ['t&g']

    assert notes[1]['fields']['Front'] == 'Math: 2 + 2 = 4'

def test_format_cards_numeric_conversion(data_processing_module):
    """Test that numeric values in fields are converted to strings."""
    MockDataFrame = data_processing_module.pd.DataFrame
    data = [
        {'Deck': 'Test Deck', 'Front': 123, 'Back': 456.78, 'Tag': 999}
    ]
    df = MockDataFrame(data)

    notes = data_processing_module.format_cards_for_ankiconnect(df)

    assert notes[0]['fields']['Front'] == '123'
    assert notes[0]['fields']['Back'] == '456.78'
    assert notes[0]['tags'] == ['999']
