#!/usr/bin/env python3
"""
Czech alphabetical sorting for markdown abbreviation lists (CLI).
Rules implemented:
- Dots are treated as spaces; all whitespace is collapsed.
- Digits sort before letters; spaces/hyphens sort before letters.
- Proper Czech collation: Č, Ř, Š, Ž have their own primary order; CH is a digraph.
- Secondary (fine) order follows a 3-step scheme: position → count → shape of diacritic.
- German ß → ss (via casefold and explicit guard); common ligatures are expanded.
- Simple interactive CLI to pick one file or all (*.md except index.md).

Note: We use a deterministic sort key for reproducibility and custom rules.
"""

import os
import re

# --- Czech alphabet order (lowercase, includes CH and primary slots for č ř š ž) ---
CZECH_ALPHABET = [
    'a', 'b', 'c', 'č', 'd', 'e', 'f', 'g', 'h', 'ch', 'i', 'j', 'k', 'l', 'm',
    'n', 'o', 'p', 'q', 'r', 'ř', 's', 'š', 't', 'u', 'v', 'w', 'x', 'y', 'z', 'ž'
]
ALPHABET_POS = {letter: idx for idx, letter in enumerate(CZECH_ALPHABET)}

# --- Secondary collation constants (secondary = POSITION*100 + COUNT*10 + SHAPE) ---
# 1) Position (hundreds)
NONE   = 0      # no diacritic (wins when primary equal)
UP     = 100    # above the letter
DOWN   = 200    # below the letter
BACK   = 300    # after the letter (to the right)
FRONT  = 400    # before the letter (to the left)
INSIDE = 500    # through/inside the letter (e.g., ł, ø)
# 2) Count (tens) — SIMPLE=0 is implicit; we add only when double/triple
SIMPLE = 0
DOUBLE = 20     # double marks (diaeresis ¨, Hungarian double-acute ˝˝)
TRIPLE = 30     # triple marks (rare, e.g., ∴)
# 3) Shape (ones) — extended list
DOT        = 1   # dot / diaeresis (· / ¨)
ACUTE      = 2   # acute/čárka (´)
MACRON     = 3   # macron (¯)
VERTICAL   = 4   # vertical bar (|)
SLASH_FWD  = 5   # forward slash (/)
SLASH_BACK = 6   # backslash (\)
CIRCUMFLEX = 7   # circumflex (ˆ)
CARON      = 8   # caron/háček (ˇ)
TILDE      = 9   # tilde (~)
BOW_UP     = 10  # cup (∪)
BOW_DOWN   = 11  # cap (∩)
CEDILLA    = 12  # cedilla/comma (¸, ˛ under; latvian lowercase ģ uses comma above)
OGONEK     = 13  # ogonek/ocásek (˛)
RING       = 14  # ring/kroužek (˚)

# --- Diacritic info: char (lowercase) -> (base_letter (lowercase), secondary_rank) ---
# Note: č ř š ž have PRIMARY positions via CZECH_ALPHABET; DIACRITIC_INFO gives only fine weights.
DIACRITIC_INFO = {
    # Czech (primary handled by alphabet; secondary shown for completeness)
    'č': ('c', UP + CARON), 'ř': ('r', UP + CARON), 'š': ('s', UP + CARON), 'ž': ('z', UP + CARON),
    # Czech (secondary-only)
    'á': ('a', UP + ACUTE), 'é': ('e', UP + ACUTE), 'í': ('i', UP + ACUTE), 'ó': ('o', UP + ACUTE),
    'ú': ('u', UP + ACUTE), 'ý': ('y', UP + ACUTE),
    'ď': ('d', UP + CARON), 'ť': ('t', UP + CARON), 'ň': ('n', UP + CARON), 'ě': ('e', UP + CARON), 'ů': ('u', UP + RING),

    # Slovak
    'ĺ': ('l', UP + ACUTE), 'ľ': ('l', UP + CARON), 'ô': ('o', UP + CIRCUMFLEX),

    # German (diaeresis = double; ß handled in normalize → 'ss')
    'ä': ('a', UP + DOUBLE + DOT), 'ö': ('o', UP + DOUBLE + DOT), 'ü': ('u', UP + DOUBLE + DOT),

    # Hungarian (double-acute)
    'ő': ('o', UP + DOUBLE + ACUTE), 'ű': ('u', UP + DOUBLE + ACUTE),

    # Polish
    'ł': ('l', INSIDE + SLASH_FWD),  # stroke through letter
    'ś': ('s', UP + ACUTE), 'ź': ('z', UP + ACUTE), 'ż': ('z', UP + DOT),
    'ą': ('a', DOWN + OGONEK), 'ę': ('e', DOWN + OGONEK),

    # Romanian (comma-below; modeled as DOWN+CEDILLA for our secondary)
    'ș': ('s', DOWN + CEDILLA), 'ț': ('t', DOWN + CEDILLA),

    # French (and neighbors)
    'à': ('a', UP + ACUTE), 'â': ('a', UP + CIRCUMFLEX), 'ã': ('a', UP + TILDE),
    'ç': ('c', DOWN + CEDILLA), 'è': ('e', UP + ACUTE), 'ê': ('e', UP + CIRCUMFLEX),
    'ë': ('e', UP + DOUBLE + DOT), 'î': ('i', UP + CIRCUMFLEX), 'ï': ('i', UP + DOUBLE + DOT),
    'õ': ('o', UP + TILDE), 'û': ('u', UP + CIRCUMFLEX), 'ÿ': ('y', UP + DOUBLE + DOT),

    # Spanish
    'ñ': ('n', UP + TILDE),

    # Danish/Norwegian
    'å': ('a', UP + RING), 'ø': ('o', INSIDE + SLASH_FWD),

    # Baltic (Latvian/Lithuanian)
    # Latvian macrons; comma-below family (lowercase ģ has comma ABOVE → treat as UP + CEDILLA)
    'ā': ('a', UP + MACRON), 'ē': ('e', UP + MACRON), 'ī': ('i', UP + MACRON), 'ū': ('u', UP + MACRON),
    'ģ': ('g', UP + CEDILLA),  # lowercase g with comma ABOVE (Latvian)
    'ķ': ('k', DOWN + CEDILLA), 'ļ': ('l', DOWN + CEDILLA), 'ņ': ('n', DOWN + CEDILLA),
    # Lithuanian ogoneks & dot
    'į': ('i', DOWN + OGONEK), 'ų': ('u', DOWN + OGONEK), 'ė': ('e', UP + DOT),

    # Maltese
    'ċ': ('c', UP + DOT), 'ġ': ('g', UP + DOT), 'ż': ('z', UP + DOT), 'ħ': ('h', INSIDE + MACRON),

    # Estonian (covered also above) 
    'õ': ('o', UP + TILDE),
}

# Typographic ligatures (Alphabetic Presentation Forms)
LIGATURES = {
    'ﬀ':'ff','ﬁ':'fi','ﬂ':'fl','ﬃ':'ffi','ﬄ':'ffl','ﬅ':'ft','ﬆ':'st',
    'Æ':'Ae','æ':'ae','Œ':'Oe','œ':'oe','Ĳ':'Ij','ĳ':'ij',
    'Ǆ':'Dž','ǅ':'Dž','ǆ':'dž','Ǉ':'Lj','ǈ':'Lj','ǉ':'lj',
    'Ǌ':'Nj','ǋ':'Nj','ǌ':'nj','Ǳ':'Dz','ǲ':'Dz','ǳ':'dz',
}

def normalize_text(text: str) -> str:
    """Normalize spacing, expand ligatures, and casefold for collation.
    - Replace dots with spaces; collapse all whitespace (incl. NBSP) to single space.
    - Expand common ligatures so they sort as separate letters (ae, oe, fi, fl…).
    - Casefold to robust lowercase; ensure ß→ss explicitly (safety guard).
    - Do NOT strip Czech diacritics here; they are handled in get_sort_key.
    """
    # Dots → spaces, normalize NBSP, collapse whitespace
    text = text.replace('.', ' ').replace('\u00A0', ' ')
    text = re.sub(r"\s+", " ", text)
    # Expand common ligatures (and compatibility letters) BEFORE casefold:
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    # Robust lowercase normalization
    s = text.casefold()            # handles ß→ss by design
    s = s.replace('ß', 'ss')       # explicit guard (idempotent)
    return s


def get_sort_key(text: str):
    """Build (primary[], secondary[]) collation key.
    Primary compares per CZECH_ALPHABET (with 'ch' digraph and primary slots for č ř š ž).
    Secondary encodes diacritics as position*100 + count*10 + shape (smaller = earlier) and 0 for plain letters.
    """
    s = normalize_text(text)
    primary, secondary = [], []
    i = 0

    while i < len(s):
        # Handle CH digraph
        if i < len(s) - 1 and s[i:i+2] == 'ch':
            primary.append(ALPHABET_POS['ch'])
            secondary.append(0)
            i += 2
            continue

        ch = s[i]

        # Space / hyphen sort before letters
        if ch in (' ', '-'):
            primary.append(-5)
            secondary.append(0)
            i += 1
            continue

        # Digits sort before letters (stable per digit)
        if ch.isdigit():
            primary.append(-10 + int(ch))
            secondary.append(0)
            i += 1
            continue

        # Letters with primary slots (incl. č ř š ž)
        if ch in ALPHABET_POS:
            primary.append(ALPHABET_POS[ch])
            secondary.append(0)
            i += 1
            continue

        # Letters with secondary diacritic info (foreign & Czech secondary)
        info = DIACRITIC_INFO.get(ch)
        if info:
            base, sec_rank = info
            primary.append(ALPHABET_POS.get(base, 500))
            secondary.append(sec_rank)
            i += 1
            continue

        # Unknown characters: push after letters
        primary.append(500)
        secondary.append(0)
        i += 1

    return (primary, secondary)


# --- Markdown parsing/formatting helpers ---

def parse_markdown_list(content: str):
    """Parse definition list into (term, definition) pairs (dt/dd on two lines)."""
    """Parse all <dt>...</dt><dd>...</dd> pairs anywhere in the block."""
    pattern = re.compile(
        r'<dt>\s*(.*?)\s*</dt>\s*<dd>\s*(.*?)\s*</dd>',
        re.IGNORECASE | re.DOTALL
    )
    return [(m.group(1), m.group(2)) for m in pattern.finditer(content)]


def format_entry(term: str, definition: str) -> str:
    return f'<dt>{term}</dt>\n\t\t<dd>{definition}</dd>'


def sort_markdown_file(filepath: str):
    """Sort a single markdown abbreviation file in place.
    Ensures <dl class="abbr-list"> ... </dl> wraps the list.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    dl_start = content.find('<dl')
    first_dt = content.find('<dt>')

    if first_dt == -1:
        print(f"  No <dt> tags found in {filepath}")
        return

    # Header: everything before existing <dl>, or before first <dt> if <dl> is missing
    if dl_start != -1:
        header = content[:dl_start].rstrip() + '\n\n'
    else:
        header = content[:first_dt].rstrip() + '\n\n'

    # Extract list part without any existing <dl> ... </dl>
    list_part = content[first_dt:] if dl_start == -1 else content[dl_start:]
    list_part = re.sub(r'^<dl.*?>\s*', '', list_part, flags=re.DOTALL)
    list_part = re.sub(r'\s*</dl>\s*$', '', list_part, flags=re.DOTALL)

    entries = parse_markdown_list(list_part)
    if not entries:
        print(f"  No entries parsed in {filepath}")
        return

    sorted_entries = sorted(entries, key=lambda x: get_sort_key(x[0]))

    output_lines = [header, '<dl class="abbr-list">', '']
    output_lines += [format_entry(t, d) for t, d in sorted_entries]
    output_lines.append('</dl>\n')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"  {os.path.basename(filepath)}: {len(sorted_entries)} entries sorted.")


# --- Simple interactive CLI ---

def choose_file_cli():
    files = [f for f in os.listdir('.') if f.endswith('.md') and f != 'index.md']
    if not files:
        print("No markdown files found.")
        return

    print("\n Available .md files:\n")
    for idx, f in enumerate(files, start=1):
        print(f"  {idx}. {f}")
    print("  a. ALL files")
    print("  q. Quit\n")

    choice = input("Select file number (or a/q): ").strip().lower()

    if choice == 'q':
        print("Exiting.")
        return
    elif choice == 'a':
        for f in files:
            sort_markdown_file(f)
        print("\n All files sorted.\n")
    elif choice.isdigit() and 1 <= int(choice) <= len(files):
        filename = files[int(choice) - 1]
        sort_markdown_file(filename)
    else:
        print("Invalid choice.")


if __name__ == '__main__':
    choose_file_cli()
