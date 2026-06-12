# ════════════════════════════════════════════════════════════════════════════
#                  X4 GAME-FILE CATALOG READER (.cat / .dat)
# ════════════════════════════════════════════════════════════════════════════
#
# X4: Foundations ships its game data as pairs of archive files:
#
#   01.cat  — a PLAIN-TEXT index: one line per packed file
#   01.dat  — every one of those files concatenated back-to-back, uncompressed
#
# Each .cat line looks like:
#
#   t/0001-l044.xml 2780065 1709634519 5d41402abc4b2a76b9719d911017c592
#   └── virtual path ┘ └size┘ └ mtime ┘ └─────────── md5 ────────────────┘
#
# Because the .dat is just a concatenation, a file's byte offset is simply the
# running total of the sizes of every entry listed before it in the same .cat.
# Reading one file out of a multi-GB archive is therefore a cheap seek + read —
# no extraction to disk required.
#
# PATCH OVERRIDES: the base game has 01.cat .. 09.cat. When Egosoft patches a
# file, the new version is appended in a HIGHER-numbered catalog under the same
# virtual path. So we process catalogs in ascending order and let later entries
# overwrite earlier ones in the index dict. A size-0 entry in a patch catalog
# means "this file was deleted" — we drop it from the index.
#
# EXTENSIONS (DLC): each extensions/<dlc>/ folder has its own ext_01..NN.cat
# chain with paths relative to the DLC folder. We register those under the
# prefix "extensions/<dlc>/..." rather than merging them over base paths,
# because DLC XML files are often *diff patches* (<diff><add .../>) rather than
# full replacements — blindly overriding the base file with them would be
# wrong. Callers that want DLC content merged (e.g. language t-files) ask for
# it explicitly via find().
#
# The *_sig.cat / *_sig.dat files are digital-signature archives with no game
# data, so they are skipped entirely.
# ════════════════════════════════════════════════════════════════════════════

import fnmatch
import hashlib
import os
import pathlib
import re
from dataclasses import dataclass

# Matches base-game catalogs ("01.cat") and extension catalogs ("ext_01.cat")
# while excluding the signature variants ("01_sig.cat", "ext_01_sig.cat").
_DATA_CAT_RE = re.compile(r'^(?:ext_)?\d+\.cat$', re.IGNORECASE)


@dataclass(frozen=True)
class CatalogEntry:
    """Where one virtual file physically lives: which .dat, at what offset."""
    dat_path: pathlib.Path  # the .dat archive holding the bytes
    offset:   int           # byte position within that .dat
    size:     int           # length in bytes
    md5:      str           # checksum from the .cat line — lets us verify reads


class CatalogIndex:
    """
    Index of every file packed in an X4 installation's .cat/.dat archives.

    Build one with CatalogIndex.from_game_dir(), then pull individual files
    with read() — nothing is ever extracted to disk unless you call extract().
    """

    def __init__(self):
        # virtual path (lowercase, forward slashes) → CatalogEntry.
        # Later catalogs overwrite earlier ones here, which is exactly the
        # patch-override rule described in the header comment.
        self.entries: dict[str, CatalogEntry] = {}
        self.cats_loaded: list[pathlib.Path] = []

    # ──────────────────────────────────────────────────────────────────────
    #  Construction
    # ──────────────────────────────────────────────────────────────────────

    @classmethod
    def from_game_dir(cls, game_dir: str | pathlib.Path) -> "CatalogIndex":
        """
        Index a full X4 installation: base catalogs first (01.cat upward),
        then every extensions/<dlc>/ext_NN.cat chain.
        """
        game_dir = pathlib.Path(game_dir)
        index = cls()

        # Base game: 01.cat .. 09.cat in ascending order so patches win.
        index._load_cat_folder(game_dir, prefix="")

        # DLCs: each folder is its own independent catalog chain. sorted()
        # gives a deterministic order, though it doesn't matter for content —
        # each DLC's files stay under its own "extensions/<name>/" prefix.
        ext_root = game_dir / "extensions"
        if ext_root.is_dir():
            for dlc_dir in sorted(ext_root.iterdir()):
                if dlc_dir.is_dir():
                    index._load_cat_folder(
                        dlc_dir, prefix=f"extensions/{dlc_dir.name.lower()}/")
        return index

    def _load_cat_folder(self, folder: pathlib.Path, prefix: str) -> None:
        """Loads every data catalog in one folder, in ascending name order."""
        if not folder.is_dir():
            return
        cat_files = sorted(p for p in folder.iterdir()
                           if _DATA_CAT_RE.match(p.name))
        for cat_path in cat_files:
            self._load_cat(cat_path, prefix)

    def _load_cat(self, cat_path: pathlib.Path, prefix: str) -> None:
        """
        Parses one .cat file and registers its entries.

        The line format is space-separated, but the virtual path itself may
        contain spaces — so we split from the RIGHT: the last three tokens are
        always size, mtime, md5, and everything before them is the path.
        """
        dat_path = cat_path.with_suffix(".dat")
        if not dat_path.exists():
            # A .cat without its .dat is unreadable — skip rather than crash,
            # since one broken pair shouldn't take down the whole index.
            return

        offset = 0
        with open(cat_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.rstrip("\n").split(" ")
                if len(parts) < 4:
                    continue  # blank/malformed line
                try:
                    size = int(parts[-3])
                except ValueError:
                    continue  # path contained something size-shaped — not a real row

                vpath = prefix + " ".join(parts[:-3]).replace("\\", "/").lower()

                if size == 0:
                    # Patch deletion marker: remove any earlier version.
                    self.entries.pop(vpath, None)
                else:
                    self.entries[vpath] = CatalogEntry(
                        dat_path=dat_path,
                        offset=offset,
                        size=size,
                        md5=parts[-1],
                    )
                # The .dat stores entries in .cat order, so every entry —
                # even one later overridden — advances the running offset.
                offset += size

        self.cats_loaded.append(cat_path)

    # ──────────────────────────────────────────────────────────────────────
    #  Lookup & reading
    # ──────────────────────────────────────────────────────────────────────

    def __contains__(self, virtual_path: str) -> bool:
        return self._norm(virtual_path) in self.entries

    @staticmethod
    def _norm(virtual_path: str) -> str:
        return virtual_path.replace("\\", "/").lower().lstrip("/")

    def find(self, pattern: str) -> list[str]:
        """
        Returns all indexed virtual paths matching a shell-style wildcard,
        e.g. find("*/t/0001-l044.xml") or find("assets/units/*/macros/*.xml").
        Results are sorted for deterministic output.
        """
        return sorted(fnmatch.filter(self.entries.keys(), pattern.lower()))

    def read(self, virtual_path: str, verify: bool = False) -> bytes:
        """
        Reads one packed file straight out of its .dat archive.

        verify=True re-hashes the bytes against the .cat's md5 — cheap
        insurance while developing; leave it off in production paths.
        """
        entry = self.entries.get(self._norm(virtual_path))
        if entry is None:
            raise FileNotFoundError(
                f"'{virtual_path}' is not in any loaded catalog")

        with open(entry.dat_path, "rb") as dat:
            dat.seek(entry.offset)
            data = dat.read(entry.size)

        if len(data) != entry.size:
            raise IOError(
                f"Short read for '{virtual_path}': wanted {entry.size} bytes, "
                f"got {len(data)} — catalog and .dat are out of sync")
        if verify and hashlib.md5(data).hexdigest() != entry.md5:
            raise IOError(
                f"MD5 mismatch for '{virtual_path}' — offset arithmetic is "
                f"wrong or the archive is corrupt")
        return data

    def extract(self, virtual_path: str, dest: str | pathlib.Path) -> pathlib.Path:
        """Writes one packed file to disk; returns the path written."""
        dest = pathlib.Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.read(virtual_path))
        return dest


# ──────────────────────────────────────────────────────────────────────────
#  Game installation discovery
# ──────────────────────────────────────────────────────────────────────────

# Steam's libraryfolders.vdf lists every drive a library lives on, as lines
# like:  "path"  "D:\\SteamLibrary"
_VDF_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')

_STEAM_SUFFIX = pathlib.Path("steamapps") / "common" / "X4 Foundations"


def find_x4_install() -> pathlib.Path | None:
    """
    Locates the X4 installation, or returns None if it can't be found.

    Strategy: read Steam's libraryfolders.vdf (covers installs on any drive),
    then fall back to a handful of well-known default paths. A directory only
    counts if it actually contains 01.cat — that's what we're here for.
    """
    candidates: list[pathlib.Path] = []

    # Steam library folders (the normal case, covers non-C: drives too)
    for steam_root in (r"C:\Program Files (x86)\Steam",
                       r"C:\Program Files\Steam"):
        vdf = pathlib.Path(steam_root) / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                for lib in _VDF_PATH_RE.findall(vdf.read_text(errors="replace")):
                    # VDF escapes backslashes ("D:\\SteamLibrary")
                    candidates.append(
                        pathlib.Path(lib.replace("\\\\", "\\")) / _STEAM_SUFFIX)
            except OSError:
                pass

    # Non-Steam fallbacks
    candidates += [
        pathlib.Path(r"C:\GOG Games\X4 Foundations"),
        pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Epic Games" / "X4Foundations",
    ]

    for c in candidates:
        if (c / "01.cat").exists():
            return c
    return None
