"""Telegram Inbox — remote service for Second Brain.

A lightweight Flask app hosted on PythonAnywhere (or any server) that:
  1. Receives Telegram messages via webhook and queues them.
  2. Serves queued messages to the local second-brain via pull API.
  3. Stores note backups pushed from the local machine.
  4. Lets the user browse notes via Telegram inline keyboard menus.
"""
