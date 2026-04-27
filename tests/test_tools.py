import pytest
from app.tools import _StateGuard
from app.models import AppState, AppMode


@pytest.fixture
def guard():
    return _StateGuard()


@pytest.fixture
def presenting_state():
    state = AppState()
    state.mode = AppMode.PRESENTING
    state.resume_page = 5
    state.qa_locked = False
    return state


@pytest.fixture
def qa_locked_state():
    state = AppState()
    state.mode = AppMode.DEFENSE_QA
    state.resume_page = 5
    state.qa_locked = True
    return state


@pytest.fixture
def idle_state():
    state = AppState()
    state.mode = AppMode.IDLE
    state.resume_page = None
    state.qa_locked = False
    return state


class TestStateGuardCanResume:
    def test_can_resume_when_not_locked(self, guard, presenting_state):
        """Test can_resume returns True when QA is not locked and resume_page exists."""
        assert guard.can_resume(presenting_state) is True

    def test_cannot_resume_when_qa_locked(self, guard, qa_locked_state):
        """Test can_resume returns False when QA is locked."""
        assert guard.can_resume(qa_locked_state) is False

    def test_cannot_resume_when_no_resume_page(self, guard, idle_state):
        """Test can_resume returns False when resume_page is None."""
        assert guard.can_resume(idle_state) is False


class TestStateGuardCanStart:
    def test_can_start_when_not_locked(self, guard, presenting_state):
        """Test can_start returns True when QA is not locked."""
        assert guard.can_start(presenting_state) is True

    def test_cannot_start_when_qa_locked(self, guard, qa_locked_state):
        """Test can_start returns False when QA is locked."""
        assert guard.can_start(qa_locked_state) is False


class TestStateGuardRedirectIfLocked:
    def test_redirect_if_locked_returns_message(self, guard, qa_locked_state):
        """Test redirect_if_locked returns a message when QA is locked."""
        msg = guard.redirect_if_locked(qa_locked_state, "presentation_start")
        assert msg is not None
        assert "presentation_start" in msg
        assert "QA mode" in msg

    def test_redirect_if_locked_returns_none_when_unlocked(self, guard, presenting_state):
        """Test redirect_if_locked returns None when QA is not locked."""
        msg = guard.redirect_if_locked(presenting_state, "presentation_start")
        assert msg is None
