"""Shared configuration for the Jobs Funnel UI."""
from pathlib import Path

from dotenv import load_dotenv

from scripts import db as scripts_db

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

TABLE = scripts_db.table_name()
EVENTS_TABLE = scripts_db.events_table_name()
