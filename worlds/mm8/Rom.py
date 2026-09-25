"""AP patch container for Mega Man 8 (PS1, NTSC-U, SLUS-00453).

The X5/X6 shape - no external xdelta, no basepatch file, the image patched in
pure Python with per-sector EDC/ECC regeneration - adapted to a THREE-track
disc. The base "ROM" is Track 1, the only track ever edited; Tracks 2 and 3
are found beside it by size and md5, and the result is one merged .bin with a
single-FILE cue (disc.merged_cue explains why that layout is exact).

Per-seed data rides in the .apmm8 as JSON: what each Lab entry holds, turned
into text edits at patch time, when the vanilla bytes are to hand; and the
options' disc edits (seed_edits.json), rolled at generation and written
whole, each carrying the vanilla bytes it expects.
"""
import hashlib
import json
import logging
import os
import shutil
from typing import TYPE_CHECKING

import settings
import Utils
from worlds.Files import APPatchExtension, APProcedurePatch

from . import damage, disc, music, palettes, pickups

if TYPE_CHECKING:
    from . import MM8World

logger = logging.getLogger()

HASH_TRACK1 = disc.TRACK_MD5[0]


class MM8Settings(settings.Group):
    class RomFile(settings.UserFilePath):
        """File path of Track 1 of the Mega Man 8 (USA) disc image - the
        "(Track 1).bin". Tracks 2 and 3 must be in the same folder."""
        description = "Mega Man 8 (USA) (Track 1).bin"
        md5s = [HASH_TRACK1]
        # NO copy_to: copying would take Track 1 away from the two audio
        # tracks it has to be patched together with. The setting links to the
        # player's dump where it is.

    rom_file: RomFile = RomFile("Mega Man 8 (USA) (Track 1).bin")

    # Mega Man's colour. The colour itself is an ordinary YAML option; this is
    # an OVERRIDE, so it can change without a new seed. Only a real colour (or
    # "random") overrides - "vanilla" here does nothing, because Archipelago
    # writes every default into host.yaml (palettes.overrides; X5's rule).
    mega_man_palette: str = palettes.UNSET


def get_base_rom_path() -> str:
    from . import MM8World
    path = MM8World.settings.rom_file
    if not os.path.exists(path):
        path = Utils.user_path(path)
    return path


def get_base_rom_bytes() -> bytes:
    path = get_base_rom_path()
    with open(path, "rb") as f:
        data = f.read()
    digest = hashlib.md5(data).hexdigest()
    if digest != HASH_TRACK1:
        raise ValueError(
            f"Mega Man 8: {os.path.basename(path)} has MD5 {digest}. Expected "
            f"Track 1 of the Redump 'Mega Man 8 (USA)' dump, {HASH_TRACK1} - "
            f"the '(Track 1).bin', not the .cue or another track.")
    return data


class MM8PatchExtension(APPatchExtension):
    game = "Mega Man 8"

    @staticmethod
    def apply_basepatch(caller: APProcedurePatch, rom: bytes) -> bytes:
        entries = {int(part): tuple(entry) for part, entry
                   in json.loads(caller.get_file("lab.json").decode("utf-8")).items()}
        seed = json.loads(caller.get_file("seed.json").decode("utf-8"))
        try:
            options = decode_edits(caller.get_file("seed_edits.json"))
        except KeyError:
            options = []       # a patch from before the options existed
        edits = (list(disc.BASE_EDITS) + disc.routine_edits(rom)
                 + disc.lab_text_edits(rom, entries) + disc.ap_block_edits(seed["stamp"])
                 + options)
        return disc.apply_edits(rom, edits)

    @staticmethod
    def apply_palettes(caller: APProcedurePatch, rom: bytes) -> bytes:
        """Mega Man's colour: the seed's choice, or a host.yaml override (X5's
        apply_palettes). Runs after apply_basepatch; the records are found by
        content, and the basepatch never touches their bytes."""
        import random

        seed_choice: dict = {}
        try:
            seed_choice = json.loads(caller.get_file("palettes.json").decode("utf-8"))
        except KeyError:
            pass                  # a patch from before the option
        # get_settings() memoises; re-read host.yaml so an edit between two
        # patches in one Launcher session is seen (X5), then restore the cache.
        cached = getattr(settings.get_settings, "_cache", None)
        try:
            settings.get_settings._cache = None
            group = settings.get_settings().mm8_options
        except Exception:
            group = None
        finally:
            settings.get_settings._cache = cached
        host_values = {target: (getattr(group, f"{target}_palette", palettes.UNSET)
                                if group is not None else palettes.UNSET)
                       for target in palettes.TARGETS}
        choices = palettes.choose(seed_choice, host_values)
        for target, value in choices.items():
            if palettes.overrides(host_values.get(target)):
                logger.info("Mega Man 8 palette %s: %s, overridden from host.yaml", target, value)
        if all((c or palettes.VANILLA).strip().lower() == palettes.VANILLA for c in choices.values()):
            return rom
        # Seeded on the player name, so re-patching reproduces a host.yaml "random".
        rng = random.Random(getattr(caller, "player_name", "") or None)
        image = bytearray(rom)
        for sector in sorted(palettes.apply(image, choices, rng)):
            disc.regenerate_sector(image, sector)
        return bytes(image)

    @staticmethod
    def apply_music(caller: APProcedurePatch, rom: bytes) -> bytes:
        """stage_music: rebuild the stage sound banks for the seed's deal and
        re-lay the SOUND region (music.apply_music, which re-parities what it
        touches and refuses a region that is not vanilla)."""
        try:
            assignment = json.loads(caller.get_file("music.json").decode("utf-8"))
        except KeyError:
            assignment = None     # a patch from before the option
        if not assignment:
            return rom
        image = bytearray(rom)
        music.apply_music(image, assignment)
        return bytes(image)


class MM8ProcedurePatch(APProcedurePatch):
    hash = [HASH_TRACK1]
    game = "Mega Man 8"
    patch_file_ending = ".apmm8"
    result_file_ending = ".cue"
    procedure = [("apply_basepatch", []), ("apply_palettes", []), ("apply_music", [])]

    @classmethod
    def get_source_data(cls) -> bytes:
        return get_base_rom_bytes()

    def patch(self, target: str) -> None:
        """Write "<name>.bin" (patched Track 1 + Tracks 2 and 3) and
        "<name>.cue". The .bin is assembled under a temporary name and only
        renamed into place once complete, so an interrupted patch never
        leaves a half-disc that the "already exists" check would accept."""
        file_name = target[:-len(self.result_file_ending)]
        bin_path, cue_path = file_name + ".bin", file_name + ".cue"
        if os.path.exists(bin_path) and os.path.exists(cue_path):
            logger.info("Patched disc + CUE already exist!")
            return
        track2, track3 = disc.find_audio_tracks(get_base_rom_path())

        super().patch(target)              # the patched Track 1, at `target`
        partial = bin_path + ".partial"
        with open(partial, "wb") as out:
            for path in (target, track2, track3):
                with open(path, "rb") as f:
                    shutil.copyfileobj(f, out, 1 << 20)
        os.remove(target)
        os.replace(partial, bin_path)
        with open(cue_path, "w", newline="\n") as f:
            f.write(disc.merged_cue(os.path.basename(bin_path)))


def lab_entries(world: "MM8World") -> dict[int, tuple[str, str | None, str | None]]:
    """{part id: (item name, owner or None when it is this player's, game)}
    for every Lab entry, from the filled multiworld."""
    from . import names
    entries = {}
    for part in names.PARTS:
        item = world.get_location(names.shop_location(part)).item
        if item.player == world.player:
            entries[names.PART_ID[part]] = (item.name, None, None)
        else:
            entries[names.PART_ID[part]] = (item.name, world.multiworld.player_name[item.player],
                                            item.game)
    return entries


QOL_OPTIONS = ("text_skip", "skip_intro_videos", "exit_stage_anytime")


def seed_edits(world: "MM8World") -> list[tuple[str, int, str, bytes, bytes]]:
    """This seed's option-driven disc edits. Rolled values come from the
    world (generate_early), so the patch writes exactly what the spoiler
    shows. An option that is off contributes nothing, so its code stays
    vanilla on the disc."""
    edits = disc.qol_edits(name for name in QOL_OPTIONS if getattr(world.options, name))
    if world.options.weapon_damage:
        edits += damage.weapon_damage_edits(world.weapon_damage_tables)
    if world.options.boss_hp_randomization:
        edits += damage.boss_hp_edits(world.boss_hp_factors)
    if world.options.boss_damage:
        edits += damage.boss_damage_edits(world.boss_damage_factors)
    if world.options.pickupsanity:
        edits += disc.pickup_edits(pickups.KEYS)
    edits += disc.max_life_edits(int(world.options.max_life))     # none at 40
    return edits


def encode_edits(edits: list[tuple[str, int, str, bytes, bytes]]) -> bytes:
    return json.dumps([[label, where, region, vanilla.hex(), payload.hex()]
                       for label, where, region, vanilla, payload in edits]).encode("utf-8")


def decode_edits(raw: bytes) -> list[tuple[str, int, str, bytes, bytes]]:
    """The inverse of encode_edits. Every edit still carries its vanilla
    bytes, so apply_edits refuses a disc they do not match."""
    return [(label, where, region, bytes.fromhex(vanilla), bytes.fromhex(payload))
            for label, where, region, vanilla, payload in json.loads(raw.decode("utf-8"))]


def write_patch(world: "MM8World", output_directory: str) -> str:
    patch = MM8ProcedurePatch(player=world.player,
                              player_name=world.multiworld.player_name[world.player])
    patch.write_file("lab.json", json.dumps(lab_entries(world)).encode("utf-8"))
    patch.write_file("seed.json", json.dumps({"stamp": world.seed_stamp()}).encode("utf-8"))
    patch.write_file("seed_edits.json", encode_edits(seed_edits(world)))
    # Resolved HERE so `random` is rolled once, at generation, and recorded.
    patch.write_file("palettes.json", json.dumps({
        target: palettes.resolve(getattr(world.options, f"{target}_palette").current_key, world.random)
        for target in palettes.TARGETS}).encode("utf-8"))
    patch.write_file("music.json", json.dumps(world.stage_music).encode("utf-8"))
    path = os.path.join(output_directory,
                        f"{world.multiworld.get_out_file_name_base(world.player)}"
                        f"{patch.patch_file_ending}")
    patch.write(path)
    return path
