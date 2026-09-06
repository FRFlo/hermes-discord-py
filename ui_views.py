"""
Module de rétro-compatibilité réexportant les vues depuis le package views/.
"""

from views import (
    AVAILABLE_MODELS,
    ApprovalView,
    CronCreateModal,
    CronDetailView,
    CronManagerView,
    CronSelect,
    ModelCustomModal,
    ModelSelect,
    ModelSelectView,
    PostResponseActionView,
    QuestionInteractiveView,
    QuestionOptionSelect,
    QuestionTextModal,
    SessionDetailView,
    SessionManagerView,
    SessionRenameModal,
    SessionSelect,
    SystemAlertView,
    ToolProgressView,
    truncate,
)

__all__ = [
    "truncate",
    "PostResponseActionView",
    "ToolProgressView",
    "ApprovalView",
    "SystemAlertView",
    "QuestionTextModal",
    "QuestionOptionSelect",
    "QuestionInteractiveView",
    "AVAILABLE_MODELS",
    "ModelCustomModal",
    "ModelSelect",
    "ModelSelectView",
    "CronCreateModal",
    "CronSelect",
    "CronManagerView",
    "CronDetailView",
    "SessionRenameModal",
    "SessionSelect",
    "SessionManagerView",
    "SessionDetailView",
]
