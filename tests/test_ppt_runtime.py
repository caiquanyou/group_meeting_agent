import pytest
from unittest.mock import MagicMock
from app.ppt_runtime import Presenter, PPTBridge
from app.models import AppState
from app.tts_service import TTSService


@pytest.fixture
def mock_tts():
    return MagicMock(spec=TTSService)


@pytest.fixture
def mock_ppt():
    return MagicMock(spec=PPTBridge)


@pytest.fixture
def presenter(mock_tts, mock_ppt):
    state = AppState()
    return Presenter(state=state, tts=mock_tts, ppt=mock_ppt)


class TestSaveCheckpoint:
    def test_save_checkpoint_returns_correct_values(self, presenter):
        """Test that save_checkpoint returns the current page and segment index."""
        # Setup
        presenter.page = 5
        presenter.index = 3

        # Act
        checkpoint = presenter.save_checkpoint()

        # Assert
        assert checkpoint["page"] == 5
        assert checkpoint["segment_index"] == 3

    def test_save_checkpoint_with_none_page(self, presenter):
        """Test save_checkpoint when page is None."""
        # Setup
        presenter.page = None
        presenter.index = 0

        # Act
        checkpoint = presenter.save_checkpoint()

        # Assert
        assert checkpoint["page"] is None
        assert checkpoint["segment_index"] == 0


class TestRestoreCheckpoint:
    def test_restore_checkpoint_sets_correct_values(self, presenter):
        """Test that restore_checkpoint sets page and index correctly."""
        # Act
        presenter.restore_checkpoint(page=7, segment_index=2)

        # Assert
        assert presenter.page == 7
        assert presenter.index == 2

    def test_restore_checkpoint_with_zero_index(self, presenter):
        """Test restore_checkpoint with segment_index=0."""
        # Act
        presenter.restore_checkpoint(page=1, segment_index=0)

        # Assert
        assert presenter.page == 1
        assert presenter.index == 0
