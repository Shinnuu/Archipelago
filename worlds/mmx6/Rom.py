"""AP patch container for Mega Man X6 (PS1, NTSC-U, SLUS-01395).

Follows the X5 world's shape, which itself improved on the MMX4 apworld: no
external xdelta executable and no separate basepatch file. The edit list is
tiny and lives in disc.py, so the vanilla image is patched in pure Python -
including the MANDATORY per-sector EDC/ECC regeneration, without which emulator
disc layers error-correct the edits back to vanilla and the patch silently does
nothing.

Any per-seed data would ride inside the .apmmx6 as JSON rather than as
APTokenMixin tokens, because raw token pokes would bypass parity regeneration.
v0.1 has none: the A1 patch is identical for every seed.
"""
import hashlib
import json
import logging
import os
from typing import TYPE_CHECKING

import settings
import Utils
from worlds.Files import APPatchExtension, APProcedurePatch

from . import disc

if TYPE_CHECKING:
    from . import MMX6World

logger = logging.getLogger()

# MD5s of the raw 2352-byte NTSC-U images this patch is built and tested
# against. BOTH are verified, 2026-08-25, by actually patching them.
#
# Redump "Mega Man X6 (USA) (Rev 1)" is the canonical dump and what players
# will almost always have. The development image is that same disc plus eight
# trailing ZERO sectors, with the only other differences confined to ISO
# filesystem metadata (sectors 16, 22-24) and a handful of data sectors around
# 222000 - none of which any patch touches.
#
# What matters, and what was measured rather than assumed: SLUS_013.95 and
# ROCK_X6.BIN are **byte-identical between the two images**, 0 differing
# sectors across both containers. So every disc offset derived on one is valid
# on the other, and patching the Redump image produces exactly the same three
# sectors with valid EDC/ECC. verify_release.py re-proves this on every run.
HASH_US_REDUMP = "237b6feddd1a88e86ab1cddc8822f03f"   # (USA) (Rev 1), canonical
HASH_US_DEV = "ae1f630f686edb48f84f8d69346bc8a8"      # Redump + 8 zero sectors
ACCEPTED_HASHES = {HASH_US_REDUMP, HASH_US_DEV}
HASH_US = HASH_US_REDUMP    # kept for callers importing the old name


class MMX6Settings(settings.Group):
    class RomFile(settings.UserFilePath):
        description = "Mega Man X6 (USA) disc image"
        copy_to = "Megaman X6.bin"
        md5s = sorted(ACCEPTED_HASHES)


def get_base_rom_path() -> str:
    from . import MMX6World
    path = MMX6World.settings.rom_file
    if not os.path.exists(path):
        path = Utils.user_path(path)
    return path


def get_base_rom_bytes() -> bytes:
    path = get_base_rom_path()
    with open(path, "rb") as f:
        data = f.read()
    digest = hashlib.md5(data).hexdigest()
    if digest not in ACCEPTED_HASHES:
        raise ValueError(
            f"Mega Man X6: supplied disc image has MD5 {digest}, which this "
            f"world has not been tested against. Expected the Redump "
            f"'Mega Man X6 (USA) (Rev 1)' dump, {HASH_US_REDUMP} (raw "
            f"2352-byte .bin).")
    return data


class MMX6PatchExtension(APPatchExtension):
    game = "Mega Man X6"

    @staticmethod
    def apply_basepatch(caller: APProcedurePatch, rom: bytes) -> bytes:
        extra: list[tuple[int, bytes, str]] = []
        try:
            seed_edits = json.loads(
                caller.get_file("seed_edits.json").decode("utf-8"))
            for entry in seed_edits:
                extra.append((entry["addr"], bytes.fromhex(entry["hex"]),
                              entry["region"]))
        except KeyError:
            pass    # no per-seed edits in this patch
        return disc.apply_basepatch(rom, extra)


class MMX6ProcedurePatch(APProcedurePatch):
    hash = sorted(ACCEPTED_HASHES)
    game = "Mega Man X6"
    patch_file_ending = ".apmmx6"
    result_file_ending = ".cue"
    procedure = [
        ("apply_basepatch", []),
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        return get_base_rom_bytes()

    def patch(self, target: str) -> None:
        file_name = target[:-4]
        if os.path.exists(file_name + ".bin") and os.path.exists(file_name + ".cue"):
            logger.info("Patched disc + CUE already exist!")
            return

        super().patch(target)
        os.rename(target, file_name + ".bin")

        rom_name = os.path.basename(file_name)
        with open(file_name + ".cue", "w", newline="\n") as f:
            f.write(f'FILE "{rom_name}.bin" BINARY\n'
                    f'  TRACK 01 MODE2/2352\n'
                    f'    INDEX 01 00:00:00\n')


def patch_rom(world: "MMX6World", patch: MMX6ProcedurePatch) -> None:
    """Attach per-seed data. v0.1 has none - the A1 patch is seed-independent,
    and everything else the seed decides is carried by slot_data and applied by
    the client at runtime."""
    patch.write_file("seed_edits.json", json.dumps([]).encode("utf-8"))
