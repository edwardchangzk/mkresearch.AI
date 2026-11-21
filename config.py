"""Deployment settings. Cloud mode switches on when MKR_SNAPSHOT_URL is set (environment variable or Streamlit
secret). In cloud mode the app only READS a data snapshot published by the scheduled GitHub job; it never depends on
Yahoo being reachable from Streamlit's servers, and it never relies on local disk surviving a restart."""
import os


def _setting(name, default=None):
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default


SNAPSHOT_URL = str(_setting("MKR_SNAPSHOT_URL") or "").rstrip("/")   # e.g. https://raw.githubusercontent.com/USER/REPO/data/snapshot
SNAPSHOT_TOKEN = _setting("MKR_SNAPSHOT_TOKEN")                      # only needed if the repository is private
CLOUD = bool(SNAPSHOT_URL)
