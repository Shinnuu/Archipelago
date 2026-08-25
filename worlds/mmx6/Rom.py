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

# MD5 of the raw 2352-byte NTSC-U image this patch is built and tested against.
#
# ONLY ONE HASH IS ACCEPTED, deliberately. X5 could accept the Redump dump as
# well because its dev image was proven to be Redump plus exactly one trailing
# zero sector, leaving every offset valid. X6 has NO such proof: trimming 1, 2,
# 4, 8 or 16 trailing sectors from our image does not reproduce the Redump
# hash, so the two differ somewhere unidentified.
#
# The difference is very likely harmless - our patch touches sectors
# 211019-211614, while ZNULL.DAT filler begins at LBA 236858, far past them -
# but "very likely" is not "verified". Add the Redump hash only after actually
# patching a Redump image and confirming the edits land, exactly as
# verify_release.py does for X5. Until then, claim support only for what is
# tested.
HASH_US = "ae1f630f686edb48f84f8d69346bc8a8"
ACCEPTED_HASHES = {HASH_US}


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
            f"world has not been tested against. Expected {HASH_US} (raw "
            f"2352-byte NTSC-U .bin).")
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
