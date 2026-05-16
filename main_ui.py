"""
X4 Foundations Empire Intelligence — Dear PyGui UI
Entry point. Loads x4_empire_state.json and renders the dashboard.

Requirements:
    pip install dearpygui

Usage:
    python main_ui.py
    python main_ui.py --json path/to/x4_empire_state.json
"""

import json
import os
import sys
import argparse
import dearpygui.dearpygui as dpg


# ── Colour palette ────────────────────────────────────────────────
BG          = (13,  17,  23,  255)   # #0d1117  window background
BG_PANEL    = (22,  27,  34,  255)   # #161b22  top bar / panels
BG_CARD     = (28,  33,  40,  255)   # #1c2128  card backgrounds
BORDER      = (33,  38,  45,  255)   # #21262d  borders
TEXT        = (201, 209, 217, 255)   # #c9d1d9  primary text
TEXT_DIM    = (139, 148, 158, 255)   # #8b949e  secondary text
TEXT_FAINT  = (61,  68,  77,  255)   # #3d444d  labels / hints
TEAL        = (45,  212, 191, 255)   # #2dd4bf  accent
AMBER       = (210, 153, 34,  255)   # #d29922  credits / warning
RED         = (248, 81,  73,  255)   # #f85149  hostile / danger
GREEN       = (63,  185, 80,  255)   # #3fb950  allied / good


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        print(f"[Error] File not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_credits(n) -> str:
    if not isinstance(n, (int, float)):
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M Cr"
    if n >= 1_000:
        return f"{n/1_000:.1f}k Cr"
    return f"{int(n):,} Cr"


def _topbar_field(label: str, value: str, colour):
    """Render a label + value pair in the top bar."""
    with dpg.group(horizontal=False):
        dpg.add_text(label.upper(), color=TEXT_FAINT)
        dpg.add_text(value, color=colour)
    dpg.add_spacer(width=20)


def build_topbar(data: dict):
    pilot    = data.get("pilot",   "Unknown")
    sector   = data.get("sector",  "Unknown")
    credits  = data.get("credits", 0)
    ships    = data.get("fleet_summary", {}).get("total_ships", "—")
    stations = len(data.get("stations", []))

    with dpg.group(horizontal=True):
        dpg.add_text("X4 · EMPIRE INTELLIGENCE", color=TEAL)
        dpg.add_spacer(width=20)
        _topbar_field("Pilot",    pilot,                   TEXT)
        _topbar_field("Sector",   f"● {sector}",           TEAL)
        _topbar_field("Credits",  format_credits(credits), AMBER)
        _topbar_field("Ships",    str(ships),              TEXT)
        _topbar_field("Stations", str(stations),           TEXT)


def build_ui(data: dict):
    with dpg.window(
        tag="primary",
        label="",
        no_title_bar=True,
        no_move=True,
        no_resize=True,
        no_close=True,
        no_scrollbar=True,
    ):
        # ── Top bar ───────────────────────────────────────────────
        build_topbar(data)
        dpg.add_separator()
        dpg.add_spacer(height=8)

        # ── Placeholder — panels go here next ─────────────────────
        dpg.add_text(
            "Dashboard loading — panels coming soon",
            color=TEXT_FAINT,
        )


def on_resize(sender, app_data):
    """Keep the primary window filling the viewport at all times."""
    dpg.set_item_width("primary",  dpg.get_viewport_width())
    dpg.set_item_height("primary", dpg.get_viewport_height())


def main():
    parser = argparse.ArgumentParser(description="X4 Empire Intelligence UI")
    parser.add_argument(
        "--json",
        default="x4_empire_state.json",
        help="Path to empire state JSON (default: x4_empire_state.json)",
    )
    args = parser.parse_args()
    data = load_json(args.json)

    dpg.create_context()

    # ── Global theme ──────────────────────────────────────────────
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,       BG)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,        BG_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_Border,         BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_Text,           TEXT)
            dpg.add_theme_color(dpg.mvThemeCol_Separator,      BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_Header,         BG_CARD)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,  BG_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,        BG_CARD)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,  12, 10)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,    8,  6)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,   6,  4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)

    dpg.bind_theme(global_theme)

    # ── Viewport & window ─────────────────────────────────────────
    dpg.create_viewport(
        title="X4 · Empire Intelligence",
        width=1200,
        height=720,
        min_width=900,
        min_height=600,
        clear_color=BG,
    )
    dpg.set_viewport_resize_callback(on_resize)

    build_ui(data)

    dpg.setup_dearpygui()
    dpg.show_viewport()

    # Size primary window to fill viewport on first frame
    dpg.set_item_width("primary",  1200)
    dpg.set_item_height("primary", 720)

    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
