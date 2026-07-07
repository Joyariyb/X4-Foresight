"""Core role: Advisors package marker — real code lives in combine.py, not here.

Kept empty on purpose: ui/web/generate_manifest.py skips every __init__.py when
staging files for the Pyodide build, so anything defined here would silently
never reach the web build. See combine.py's docstring for the full story.
"""
