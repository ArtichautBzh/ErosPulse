"""
theme.py
========
Palette de couleurs et polices centralisées, pour garder un look
cohérent sur toutes les pages de l'application.
"""

# Palette : violet/rose profond, cohérent avec l'univers Lovense,
# sur fond sombre pour un rendu "app moderne".
BG_DARK = "#15111c"
BG_PANEL = "#1f1a29"
BG_CARD = "#271f34"

ACCENT = "#e0468b"        # rose/magenta principal
ACCENT_HOVER = "#ef5c9c"
ACCENT_MUTED = "#8a5fb0"  # violet secondaire

TEXT_PRIMARY = "#f5f2f8"
TEXT_SECONDARY = "#b6a9c7"
TEXT_MUTED = "#7c6f8d"

SUCCESS = "#4fd18b"
WARNING = "#e0b34f"
DANGER = "#e05a5a"

FONT_FAMILY = "Segoe UI"        # fallback géré par tkinter si absente
FONT_TITLE = (FONT_FAMILY, 28, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 13)
FONT_BODY = (FONT_FAMILY, 11)
FONT_BODY_BOLD = (FONT_FAMILY, 11, "bold")
FONT_BUTTON = (FONT_FAMILY, 12, "bold")
FONT_SMALL = (FONT_FAMILY, 9)

WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 620
