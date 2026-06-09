#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the split OMRS engine."""

from omrs.cli import main
from omrs.common import (
    ATTACHMENTS_DIR,
    FILE_PATTERN,
    HISTORY_CSV,
    HISTORY_HEADERS,
    MASTERY_CSV,
    MASTERY_HEADERS,
    OMRS_DIR,
    QUESTIONS_DIR,
    SESSIONS_CSV,
    SESSIONS_HEADERS,
    history_path,
    load_csv,
    mastery_path,
    omrs_data_dir,
    questions_root,
    save_csv,
    sessions_path,
)
from omrs.creation import create_question
from omrs.exporting import export_schedule_artifact, export_schedule_html
from omrs.feedback import process_feedback
from omrs.indexing import build_index, scan_vault
from omrs.scheduling import (
    compute_mastery_update,
    get_items_by_uids,
    schedule_questions,
    time_decay,
)
from omrs.server import OMRSHandler
from omrs.sessions import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    mark_session_completed,
)
from omrs.stats import get_question_content, get_stats


if __name__ == "__main__":
    main()
